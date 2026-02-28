package com.iai.flink;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.functions.FilterFunction;
import org.apache.flink.api.common.serialization.SimpleStringSchema;
import org.apache.flink.api.connector.sink2.Sink;
import org.apache.flink.api.connector.sink2.SinkWriter;
import org.apache.flink.api.connector.sink2.WriterInitContext;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.http.client.methods.HttpPost;
import org.apache.http.entity.StringEntity;
import org.apache.http.impl.client.CloseableHttpClient;
import org.apache.http.impl.client.HttpClients;

import java.io.IOException;
import java.io.Serializable;

/**
 * 实时异常检测 Flink 任务（兼容 Flink 2.x）
 * 从 Kafka 读取传感器数据，检测到 ANOMALY 状态时，调用 AgentServer 的 Webhook。
 */
public class AnomalyDetectionJob {

    public static void main(String[] args) throws Exception {
        // 1. 设置执行环境
        final StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();

        // 2. 配置 Kafka Source（使用新版 KafkaSource API，Flink 2.x 兼容）
        KafkaSource<String> source = KafkaSource.<String>builder()
                .setBootstrapServers("192.168.0.105:9092")
                .setTopics("raw_sensor_data")
                .setGroupId("flink-iai-group")
                .setStartingOffsets(OffsetsInitializer.latest())
                .setValueOnlyDeserializer(new SimpleStringSchema())
                .build();

        // 3. 读取流
        DataStream<String> stream = env.fromSource(source, WatermarkStrategy.noWatermarks(), "Kafka Source");

        // 4. 实时检测逻辑：过滤出状态为 ANOMALY 的数据
        DataStream<String> anomalyStream = stream.filter(new FilterFunction<String>() {
            private final ObjectMapper mapper = new ObjectMapper();
            @Override
            public boolean filter(String value) throws Exception {
                JsonNode node = mapper.readTree(value);
                return node.has("status") && "ANOMALY".equals(node.get("status").asText());
            }
        });

        // 5. 调用 AgentServer Webhook（使用 Flink 2.x 新版 Sink API）
        anomalyStream.sinkTo(new HttpWebhookSink());

        System.out.println("⚡ Flink 实时检测任务已启动，正在监听 Kafka: raw_sensor_data...");
        env.execute("IIoT Anomaly Detection Job");
    }

    /**
     * 自定义 Sink（Flink 2.x 新版 API）：将异常数据发送至 AgentServer Webhook
     */
    public static class HttpWebhookSink implements Sink<String>, Serializable {
        private static final long serialVersionUID = 1L;

        @Override
        public SinkWriter<String> createWriter(WriterInitContext context) throws IOException {
            return new HttpWebhookWriter();
        }

        /**
         * 实际执行 HTTP 调用的 SinkWriter
         */
        private static class HttpWebhookWriter implements SinkWriter<String> {
            private final String webhookUrl = "http://192.168.0.105:8000/api/v1/alerts";

            @Override
            public void write(String element, Context context) throws IOException, InterruptedException {
                System.out.println("🚨 Flink [发现异常数据] -> 正在请求 AgentServer: " + element);
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
                // 无需缓冲区刷新操作
            }

            @Override
            public void close() throws Exception {
                // 无需释放资源
            }
        }
    }
}
