#!/bin/bash

RUN_TESTS="google:ubuntu-24.04-64:tests/main/ack google:ubuntu-22.04-64:tests/main/ack google:ubuntu-24.04-64:tests/main/alias google:ubuntu-22.04-64:tests/main/alias"
WRITE_DIR="/tmp/features"
NUM_ATTEMPTS=2

export SPREAD_TAG_FEATURES=all

mkdir -p "$WRITE_DIR"

for i in $(seq 1 $NUM_ATTEMPTS); do

    /home/katie/go/bin/spread -artifacts ${WRITE_DIR}/features-artifacts ${RUN_TESTS} | tee ${WRITE_DIR}/spread-logs.txt

    if [ -f "$WRITE_DIR"/spread-logs.txt ]; then
        ./tests/lib/external/snapd-testing-tools/utils/log-parser ${WRITE_DIR}/spread-logs.txt --output ${WRITE_DIR}/spread-results.json
        ./tests/lib/external/snapd-testing-tools/utils/log-analyzer list-reexecute-tasks "${RUN_TESTS}" ${WRITE_DIR}/spread-results.json > ${WRITE_DIR}/failed-tests.txt
    else
        touch "${WRITE_DIR}/failed-tests.txt"
    fi

    ./tests/lib/compose-features.py \
        --dir ${WRITE_DIR}/features-artifacts/feature-tags \
        --output ${WRITE_DIR}/composed-feature-tags \
        --failed-tests "$(cat ${WRITE_DIR}/failed-tests.txt)" \
        --run-attempt ${i}
    
    if [ -z "$(cat ${WRITE_DIR}/failed-tests.txt)" ]; then
        break
    fi

    RUN_TESTS="$(cat ${WRITE_DIR}/failed-tests.txt)"
done

./tests/lib/compose-features.py \
    --dir ${WRITE_DIR}/composed-feature-tags \
    --output ${WRITE_DIR}/final-feature-tags \
    --replace-old-runs


echo "Your feature tags can be found in $WRITE_DIR/final-feature-tags"