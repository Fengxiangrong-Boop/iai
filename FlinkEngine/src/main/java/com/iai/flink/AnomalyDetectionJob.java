package com.iai.flink;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.functions.FilterFunction;
import org.apache.flink.api.common.functions.MapFunction;
import org.apache.flink.api.common.serialization.SimpleStringSchema;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.api.functions.sink.SinkFunction;
import org.apache.http.client.methods.HttpPost;
import org.apache.http.entity.StringEntity;
import org.apache.http.impl.client.CloseableHttpClient;
import org.apache.http.impl.client.HttpClients;

/**
 * 实时异常检测 Flink 任务
 * 从 Kafka 读取传感器数据，检测到 ANOMALY 状态时，调用 AgentServer 的 Webhook。
 */
public class AnomalyDetectionJob {

    public static void main(String[] args) throws Exception {
        // 1. 设置执行环境
        final StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();

        // 2. 配置 Kafka Source
        KafkaSource<String> source = KafkaSource.<String>builder()
                .setBootstrapServers("192.168.0.105:9092")
                .setTopics("raw_sensor_data")
                .setGroupId("flink-group")
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
                // 检查 status 字段是否为 ANOMALY
                return node.has("status") && "ANOMALY".equals(node.get("status").asText());
            }
        });

        // 5. 调用 AgentServer Webhook (自定义 Sink)
        anomalyStream.addSink(new HttpWebhookSink());

        System.out.println("⚡ Flink 实时检测任务已启动，正在监听 Kafka: raw_sensor_data...");
        env.execute("IIoT Anomaly Detection Job");
    }

    /**
     * 自定义 Sink：将异常数据发送至 AgentServer Webhook
     */
    public static class HttpWebhookSink implements SinkFunction<String> {
        private final String webhookUrl = "http://127.0.0.1:8000/api/v1/alerts";

        @Override
        public void invoke(String value, Context context) throws Exception {
            System.out.println("🚨 Flink [发现异常数据] -> 正在请求 AgentServer: " + value);

            try (CloseableHttpClient httpClient = HttpClients.createDefault()) {
                HttpPost httpPost = new HttpPost(webhookUrl);
                StringEntity entity = new StringEntity(value, "UTF-8");
                httpPost.setEntity(entity);
                httpPost.setHeader("Content-type", "application/json");

                httpClient.execute(httpPost);
                System.out.println("✅ 已下发智能诊断任务。");
            } catch (Exception e) {
                System.err.println("❌ 调用 AgentServer 失败: " + e.getMessage());
            }
        }
    }
}
