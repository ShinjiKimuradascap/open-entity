#!/bin/bash
export PATH="/home/moco/workspace/nodejs/bin:$PATH"
export NVM_DIR=""
unset NVM_DIR
exec npx "$@"
