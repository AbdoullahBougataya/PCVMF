# Yamcs server from the official release archive (there is no official runtime image).
FROM eclipse-temurin:17-jre

ARG YAMCS_VERSION=5.13.6
ARG TARGETARCH
RUN set -eu; \
    case "$TARGETARCH" in \
      amd64) arch=x86_64; sha=60d643c69b89b0c66d8fc20665c51b864f25f7ee1533ee1f35c5aa28170ad34b ;; \
      arm64) arch=aarch64; sha=0a629b10246e73e41885511b7a2429e0d5dd2afa45e5972bc7f61256ef09e992 ;; \
      *) echo "unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/yamcs.tar.gz \
      "https://github.com/yamcs/yamcs/releases/download/yamcs-${YAMCS_VERSION}/yamcs-${YAMCS_VERSION}-linux-${arch}.tar.gz"; \
    echo "$sha  /tmp/yamcs.tar.gz" | sha256sum -c -; \
    mkdir /opt/yamcs; \
    tar -xzf /tmp/yamcs.tar.gz -C /opt/yamcs --strip-components=1; \
    rm /tmp/yamcs.tar.gz

COPY etc/ /opt/yamcs/etc/
EXPOSE 8090 10015/udp
WORKDIR /opt/yamcs
CMD ["bin/yamcsd"]
