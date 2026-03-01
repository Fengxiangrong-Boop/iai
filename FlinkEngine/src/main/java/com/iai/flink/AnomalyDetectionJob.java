package com.iai.flink;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.functions.MapFunction;
import org.apache.flink.api.common.serialization.SimpleStringSchema;
import org.apache.flink.api.common.typeinfo.Types;
import org.apache.flink.api.connector.sink2.Sink;
import org.apache.flink.api.connector.sink2.SinkWriter;
import org.apache.flink.api.connector.sink2.WriterInitContext;
import org.apache.flink.api.java.tuple.Tuple2;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.api.functions.windowing.ProcessWindowFunction;
import org.apache.flink.streaming.api.windowing.assigners.SlidingProcessingTimeWindows;
import org.apache.flink.streaming.api.windowing.windows.TimeWindow;
import org.apache.flink.util.Collector;
import org.apache.http.client.methods.HttpPost;
import org.apache.http.entity.StringEntity;
import org.apache.http.impl.client.CloseableHttpClient;
import org.apache.http.impl.client.HttpClients;

import java.io.IOException;
import java.io.Serializable;
import java.time.Duration;

/**
 * 实时异常检测 Flink 任务（兼容 Flink 2.x）
 * 不再依赖预设的 status 标签，而是使用滑动窗口计算近 10 秒的动态均值。
 * 如果温度或震动均值超过动态阈值，则主动判定为 ANOMALY，并回调 AgentServer。
 */
public class AnomalyDetectionJob {

    public static void main(String[] args) throws Exception {
        final StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();

        KafkaSource<String> source = KafkaSource.<String>builder()
                .setBootstrapServers("192.168.0.105:9092")
                .setTopics("raw_sensor_data")
                .setGroupId("flink-iai-anomaly-group")
                .setStartingOffsets(OffsetsInitializer.latest())
                .setValueOnlyDeserializer(new SimpleStringSchema())
                .build();

        DataStream<String> stream = env.fromSource(source, WatermarkStrategy.noWatermarks(), "Kafka Source");

        // 1. 解析 JSON 并提取 Tuple2<设备ID, JsonNode>
        DataStream<Tuple2<String, JsonNode>> parsedStream = stream
                .map(new MapFunction<String, Tuple2<String, JsonNode>>() {
                    private final ObjectMapper mapper = new ObjectMapper();

                    @Override
                    public Tuple2<String, JsonNode> map(String value) throws Exception {
                        JsonNode node = mapper.readTree(value);
                        return new Tuple2<>(node.get("device_id").asText(), node);
                    }
                }).returns(Types.TUPLE(Types.STRING, Types.GENERIC(JsonNode.class)));

        // 2. 核心：设定 10秒窗口，步长 2秒 的滑动窗口进行均值与突变检测
        DataStream<String> anomalyStream = parsedStream
                .keyBy(t -> t.f0)
                .window(SlidingProcessingTimeWindows.of(Duration.ofSeconds(10), Duration.ofSeconds(2)))
                .process(new AnomalyEvaluator());

        // 3. 将检测出的真实异常发送到 Webhook
        anomalyStream.sinkTo(new HttpWebhookSink());

        System.out.println("⚡ Flink 智能滑窗异常检测任务已启动，正在监听 Kafka: raw_sensor_data...");
        env.execute("IIoT Advanced Anomaly Detection Job");
    }

    /**
     * 滑动窗口处理逻辑：在窗口内计算均值，判断是否真实超标
     */
    public static class AnomalyEvaluator
            extends ProcessWindowFunction<Tuple2<String, JsonNode>, String, String, TimeWindow> {
        private static final ObjectMapper mapper = new ObjectMapper();

        // 设定的工业预警阈值
        private static final double TEMP_THRESHOLD = 65.0;
        private static final double VIB_THRESHOLD = 1.2;

        @Override
        public void process(String deviceId, Context context, Iterable<Tuple2<String, JsonNode>> elements,
                Collector<String> out) throws Exception {
            double sumTemp = 0.0;
            double sumVib = 0.0;
            int count = 0;

            JsonNode lastNode = null;

            for (Tuple2<String, JsonNode> element : elements) {
                sumTemp += element.f1.get("temperature").asDouble();
                sumVib += element.f1.get("vibration").asDouble();
                count++;
                lastNode = element.f1;
            }

            if (count > 0) {
                double avgTemp = sumTemp / count;
                double avgVib = sumVib / count;

                // 如果计算出的平均值超标，则判定为真实异常
                if (avgTemp > TEMP_THRESHOLD || avgVib > VIB_THRESHOLD) {
                    ObjectNode alertPayload = mapper.createObjectNode();
                    alertPayload.put("device_id", deviceId);
                    alertPayload.put("status", "ANOMALY");
                    alertPayload.put("temperature", Math.round(avgTemp * 100.0) / 100.0);
                    alertPayload.put("vibration", Math.round(avgVib * 1000.0) / 1000.0);

                    if (lastNode != null && lastNode.has("timestamp")) {
                        alertPayload.put("timestamp", lastNode.get("timestamp").asText());
                    } else {
                        alertPayload.put("timestamp", java.time.Instant.now().toString());
                    }

                    alertPayload.put("trigger_reason", avgTemp > TEMP_THRESHOLD
                            ? "10秒平均温度突变 (" + alertPayload.get("temperature").asDouble() + " > " + TEMP_THRESHOLD + ")"
                            : "10秒平均震动超标 (" + alertPayload.get("vibration").asDouble() + " > " + VIB_THRESHOLD + ")");

                    out.collect(alertPayload.toString());
                }
            }
        }
    }

    public static class HttpWebhookSink implements Sink<String>, Serializable {
        private static final long serialVersionUID = 1L;

        @Override
        public SinkWriter<String> createWriter(WriterInitContext context) throws IOException {
            return new HttpWebhookWriter();
        }

        private static class HttpWebhookWriter implements SinkWriter<String> {
            private final String webhookUrl = System.getenv().getOrDefault(
                    "AGENT_SERVER_URL",
                    "http://172.18.0.1:8000/api/v1/alerts");

            @Override
            public void write(String element, Context context) throws IOException, InterruptedException {
                System.out.println("🚨 Flink [滑窗算法捕获异常] -> 正在请求 AgentServer: " + element);
                try (CloseableHttpClient httpClient = HttpClients.createDefault()) {
                    HttpPost httpPost = new HttpPost(webhookUrl);
                    StringEntity entity = new StringEntity(element, "UTF-8");
                    httpPost.setEntity(entity);
                    httpPost.setHeader("Content-type", "application/json");
                    httpClient.execute(httpPost);
                    System.out.println("✅ 已下发智能诊断任务。");
                } catch (Exception e) {
                    System.err.println("❌ 调用 AgentServer 失败: " + e.getMessage());
                }
            }

            @Override
            public void flush(boolean endOfInput) throws IOException, InterruptedException {
            }

            @Override
            public void close() throws Exception {
            }
        }
    }
}
