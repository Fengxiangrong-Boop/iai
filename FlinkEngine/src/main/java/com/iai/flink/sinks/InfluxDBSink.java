package com.iai.flink.sinks;

import com.fasterxml.jackson.databind.node.ObjectNode;
import org.apache.flink.api.connector.sink2.Sink;
import org.apache.flink.api.connector.sink2.SinkWriter;
import org.apache.flink.api.connector.sink2.WriterInitContext;

import java.io.IOException;
import java.io.Serializable;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

/**
 * 实时写 InfluxDB 的 Sink
 */
public class InfluxDBSink implements Sink<ObjectNode>, Serializable {
    private static final long serialVersionUID = 1L;

    @Override
    public SinkWriter<ObjectNode> createWriter(WriterInitContext context) throws IOException {
        return new InfluxDBWriter();
    }

    private static class InfluxDBWriter implements SinkWriter<ObjectNode> {
        private final HttpClient httpClient;
        private final String influxUrl;
        private final String token;

        public InfluxDBWriter() {
            this.httpClient = HttpClient.newHttpClient();
            String host = System.getenv().getOrDefault("INFLUXDB_HOST", "192.168.0.105");
            String org = System.getenv().getOrDefault("INFLUXDB_ORG", "iai_org");
            String bucket = System.getenv().getOrDefault("INFLUXDB_BUCKET", "iai");
            this.influxUrl = String.format("http://%s:8086/api/v2/write?org=%s&bucket=%s&precision=s", host, org, bucket);
            this.token = System.getenv().getOrDefault("INFLUXDB_TOKEN", "my-super-secret-auth-token");
        }

        @Override
        public void write(ObjectNode element, Context context) {
            try {
                // Line protocol format:
                // sensor_agg_1m,device_id=PUMP_01 temperature_avg=45.5,vibration_max=0.52
                String lineProtocol = String.format("sensor_agg_1m,device_id=%s temperature_avg=%.2f,vibration_max=%.3f,anomaly_count=%d",
                        element.get("device_id").asText(),
                        element.get("temperature_avg").asDouble(),
                        element.get("vibration_max").asDouble(),
                        element.get("anomaly_count").asInt());

                HttpRequest request = HttpRequest.newBuilder()
                        .uri(URI.create(influxUrl))
                        .header("Authorization", "Token " + token)
                        .header("Content-Type", "text/plain; charset=utf-8")
                        .POST(HttpRequest.BodyPublishers.ofString(lineProtocol))
                        .build();

                HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
                if (response.statusCode() >= 400) {
                    System.err.println("❌ Flink InfluxDB Write Error: " + response.body());
                }
            } catch (Exception e) {
                System.err.println("❌ Flink InfluxDB Sink Error: " + e.getMessage());
            }
        }

        @Override
        public void flush(boolean endOfInput) {}
        @Override
        public void close() {}
    }
}
