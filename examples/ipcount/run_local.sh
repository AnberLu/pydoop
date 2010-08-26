#!/bin/bash

nargs=1
if [ $# -lt ${nargs} ]; then
    echo "USAGE: $(basename $0) INPUT"
    exit 2
fi
INPUT=$1

cut -d " " -f 1 ${INPUT}/* | sort | uniq -c | sort -k1,1nr | head -n 5