#!/bin/bash
set -eux

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

./build-and-push.sh

ssh -t tubsmaster@192.168.215.10 "cd /volume1/@home/tubsmaster/dockercompose/solaredge2mqtt; docker compose pull && (docker compose down || true) && docker compose up -d && timeout 8 docker compose logs -f || true"

