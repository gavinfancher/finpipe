FROM tabulario/spark-iceberg:3.5.5_1.8.1

# Copy spark-defaults.conf first so we can use it to pre-cache packages
COPY spark-defaults.conf /opt/spark/conf/spark-defaults.conf

# Pre-download packages defined in spark-defaults.conf
# This caches them in the image so container startup is faster
RUN /opt/spark/bin/spark-shell \
    --properties-file /opt/spark/conf/spark-defaults.conf \
    -e "println(\"Packages cached successfully\")" && \
    echo "Package cache complete"
