FROM nginx:1.15.1

USER root
ENV INSTALL_DIR="/opt/nginx"


WORKDIR /opt/sentry-analytics

RUN mkdir -p reports scripts $INSTALL_DIR /opt/nginx/www /etc/apache2

RUN apt-get update && apt-get install -y python3 python3-pip apache2-utils && \
    pip3 install requests python-dateutil unicodecsv numpy utm sklearn scipy shapely && \
    rm -rf /var/lib/apt/lists/*

ADD scripts /opt/sentry-analytics/scripts

Add data /opt/sentry-analytics/data

ADD nginx.conf /etc/nginx/

ADD reports/dummy.html /opt/nginx/www/report.html

RUN ln -sf /dev/stdout /var/log/nginx/access.log && \
    ln -sf /dev/stderr /var/log/nginx/error.log

EXPOSE 8080

CMD /opt/sentry-analytics/scripts/cron-loader.sh
