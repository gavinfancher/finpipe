FROM tabulario/spark-iceberg:3.5.5_1.8.1

# Pre-download the packages so they're cached
RUN /opt/spark/bin/spark-shell --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    -e "println(\"Packages installed\")" || true