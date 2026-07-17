FROM kczelthy/zango:latest

RUN apt-get update && apt-get install -y net-tools sudo && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir pytest pytest-html

ARG HOST_UID=1000
ARG HOST_GID=1000

RUN groupadd -o -g $HOST_GID -r zango_user && \
    adduser --uid $HOST_UID --gid $HOST_GID --disabled-password --gecos "" zango_user && \
    echo 'zango_user ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers

USER zango_user

COPY init.sh /zango/
COPY scripts/sync_providers.sh /zango/scripts/sync_providers.sh
WORKDIR /zango/
CMD ["/bin/sh", "init.sh"]
