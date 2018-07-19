#!/bin/bash

# Set these environment variables
#DOCKER_USER // dockerhub credentials. If unset, will not deploy
#DOCKER_AUTH
#ORG // optional

set -e

#how often data is built (default once a day)
BUILD_INTERVAL=${BUILD_INTERVAL:-1}
#Substract one day, because first wait hours are computed before each build
BUILD_INTERVAL_SECONDS=$((($BUILD_INTERVAL - 1)*24*3600))
#start build at this time (GMT):
BUILD_TIME=${BUILD_TIME:-23:00:00}

htpasswd -cb /etc/apache2/.htpasswd ${USER_NAME:-user} ${USER_PASS:-test}

nginx &

cd scripts

echo "Generating first sentry report..."

python3 zero_routing.py

mv /opt/sentry-analytics/reports/* /opt/nginx/www/

echo "Sentry report updated"

set +e

while true; do
    if [[ "$BUILD_INTERVAL" -gt 0 ]]; then
        SLEEP=$(($(date -u -d $BUILD_TIME +%s) - $(date -u +%s) + 1))
        if [[ "$SLEEP" -le 0 ]]; then
            #today's build time is gone, start counting from tomorrow
            SLEEP=$(($SLEEP + 24*3600))
        fi
        SLEEP=$(($SLEEP + $BUILD_INTERVAL_SECONDS))

        echo "Sleeping $SLEEP seconds until the next build ..."
        sleep $SLEEP
    fi

    echo "Generating new sentry report..."
    if [ -v SLACK_WEBHOOK_URL ]; then
        curl -X POST -H 'Content-type: application/json' \
             --data '{"text":"Generating new sentry report\n"}' $SLACK_WEBHOOK_URL
    fi

    python3 zero_routing.py

    if [ $? != 0 ]; then
        echo "Error when updating sentry report"
        if [ -v SLACK_WEBHOOK_URL ]; then
            curl -X POST -H 'Content-type: application/json' \
                --data '{"text":"Failed to generate new sentry report\n"}' $SLACK_WEBHOOK_URL
        fi
    else
        mv /opt/sentry-analytics/reports/* /opt/nginx/www/
        echo "Sentry report updated"
        if [ -v SLACK_WEBHOOK_URL ]; then
            curl -X POST -H 'Content-type: application/json' \
                --data '{"text":"Sentry report updated\n"}' $SLACK_WEBHOOK_URL
        fi
    fi

    if [[ "$BUILD_INTERVAL" -le 0 ]]; then
        #run only once
        exit 0
    fi
done
