package com.iai.flink;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.iai.flink.sinks.InfluxDBSink;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.functions.AggregateFunction;
import org.apache.flink.api.common.functions.MapFunction;
import org.apache.flink.api.common.serialization.SimpleStringSchema;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.api.windowing.assigners.TumblingProcessingTimeWindows;
import org.apache.flink.streaming.api.windowing.time.Time;
import org.apache.flink.api.java.tuple.Tuple2;

import java.time.Duration;

/**
 * Job 2: 1 分钟窗口指标聚合统计
 *  计算 avg(temperature), max(vibration), count(anomaly) 等，并写入 InfluxDB。
 */
public class MetricsAggregationJob {

    public static void main(String[] args) throws Exception {
        final StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();

        KafkaSource<String> source = KafkaSource.<String>builder()
                .setBootstrapServers("192.168.0.105:9092")
                .setTopics("raw_sensor_data")
                .setGroupId("flink-iai-agg-group")
                .setStartingOffsets(OffsetsInitializer.latest())
                .setValueOnlyDeserializer(new SimpleStringSchema())
                .build();

        DataStream<String> stream = env.fromSource(source, WatermarkStrategy.forBoundedOutOfOrderness(Duration.ofSeconds(5)), "Kafka Source");

        // 映射 JSON，并提取设备ID作为Key
        DataStream<Tuple2<String, JsonNode>> parsedStream = stream.map(new MapFunction<String, Tuple2<String, JsonNode>>() {
            private final ObjectMapper mapper = new ObjectMapper();
            @Override
            public Tuple2<String, JsonNode> map(String value) throws Exception {
                JsonNode node = mapper.readTree(value);
                return new Tuple2<>(node.get("device_id").asText(), node);
            }
        });

        // 基于 Key 分组，开设 1 分钟滚动窗口，执行聚合计算
        DataStream<ObjectNode> aggStream = parsedStream
                .keyBy(t -> t.f0)
                .window(TumblingProcessingTimeWindows.of(Time.minutes(1)))
                .aggregate(new SensorAggregator());

        // 写回 InfluxDB aggregated_metrics
        aggStream.sinkTo(new InfluxDBSink());

        System.out.println("⚡ Flink 实时聚合任务已启动 (1 min windows)...");
        env.execute("IIoT Metrics Aggregation Job");
    }

    private static class SensorAggregator implements AggregateFunction<Tuple2<String, JsonNode>, AggResult, ObjectNode> {
        @Override
        public AggResult createAccumulator() {
            return new AggResult();
        }

        @Override
        public AggResult add(Tuple2<String, JsonNode> value, AggResult acc) {
            JsonNode node = value.f1;
            if (acc.device_id == null) acc.device_id = value.f0;
            
            acc.sumTemperature += node.get("temperature").asDouble();
            acc.maxVibration = Math.max(acc.maxVibration, node.get("vibration").asDouble());
            if ("ANOMALY".equals(node.get("status").asText())) {
                acc.anomalyCount++;
            }
            acc.count++;
            return acc;
        }

        @Override
        public ObjectNode getResult(AggResult acc) {
            ObjectMapper mapper = new ObjectMapper();
            ObjectNode result = mapper.createObjectNode();
            result.put("device_id", acc.device_id);
            result.put("temperature_avg", acc.count > 0 ? acc.sumTemperature / acc.count : 0.0);
            result.put("vibration_max", acc.maxVibration);
            result.put("anomaly_count", acc.anomalyCount);
            return result;
        }

        @Override
        public AggResult merge(AggResult a, AggResult b) {
            a.sumTemperature += b.sumTemperature;
            a.maxVibration = Math.max(a.maxVibration, b.maxVibration);
            a.count += b.count;
            a.anomalyCount += b.anomalyCount;
            return a;
        }
    }

    private static class AggResult {
        String device_id;
        double sumTemperature = 0.0;
        double maxVibration = 0.0;
        int count = 0;
        int anomalyCount = 0;
    }
}
