#!/bin/bash
set -eux

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

IMAGE_URL=tubsmaster/solaredge2mqtt

# build docker image and push - target_platform= 'linux/amd64' 'linux/arm64' 'linux/arm64,linux/amd64'
TARGET_PLATFORM='linux/amd64'
#docker buildx prune -a -f
docker buildx build --pull --push --platform ${TARGET_PLATFORM} --output='type=image' -t ${IMAGE_URL} .

