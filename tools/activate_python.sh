#!/bin/bash
# THIS FILE IS GENERATED BY tools/setup_anaconda.sh
if [ -z "${PS1:-}" ]; then
    PS1=__dummy__
fi
. /home/fangzhex/anaconda3/etc/profile.d/conda.sh && conda deactivate && conda activate muskit
