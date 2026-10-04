ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ENV LANG=en_US.UTF-8
COPY ./llvm-snapshot.gpg.key ./properties.sh ./setup-android-sdk.sh ./setup-cgct.sh ./setup-ubuntu.sh /tmp/termux-packages/scripts/
COPY ./build/termux_download.sh /tmp/termux-packages/scripts/build/

# Match the builder setup shipped with the pinned Termux recipes.
RUN apt-get update && \
    apt-get -yq upgrade && \
    apt-get install -yq sudo lsb-release software-properties-common && \
    userdel ubuntu && \
    useradd -u 1001 -U -m -s /bin/bash builder && \
    echo 'builder ALL=(root) NOPASSWD:ALL' > /etc/sudoers.d/builder && \
    chmod 0440 /etc/sudoers.d/builder && \
    chmod a+rx /tmp/termux-packages/scripts/*.sh /tmp/termux-packages/scripts/build/termux_download.sh && \
    su - builder -c "TERMUX_PKGS__BUILD__IS_DOCKER_BUILD=true /tmp/termux-packages/scripts/setup-ubuntu.sh" && \
    su - builder -c "TERMUX_PKGS__BUILD__IS_DOCKER_BUILD=true /tmp/termux-packages/scripts/setup-android-sdk.sh" && \
    /usr/bin/python3.12 -c 'import sys; assert sys.version_info[:2] == (3, 12)'

USER builder:builder
WORKDIR /home/builder/termux-packages
