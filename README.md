# digitransit-sentry-analytics

[![Build](https://api.travis-ci.org/HSLdevcom/digitransit-sentry-analytics.svg?branch=master)](https://travis-ci.org/HSLdevcom/digitransit-sentry-analytics)

Sentry issue filtering and processing. Python scripts are designed to be run on python 3.

## Basic usage

* Environmental variables
  * SENTRY_BASE_URL - mandatory, defines base url for the sentry API that ends with /api/<api version>/
  * SENTRY_TOKEN - mandatory, authentication token
  * ZERO_ROUTES_ID - mandatory for zero_routing.py script, issue ID
  * DISABLE_CACHE - optional, if true, no caching of fetched events

As of now, this project can only be used for processing *Zero routes found* routing issue.
This project contains zero_routing.py script that fetches events related to that issue,
filters out events with known issues, and generates a HTML report and CSV files from those events.

By default, the script caches the events in results.dat file and does not fetch them again
unless that file is deleted. Alternatively, you can use environmental variable DISABLE_CACHE=true
to not cache the events. If script executes succesfully, HTML report and CSV files should be found
under reports directory.

## Docker, cron and nginx

* Additional environmental variables
  * BUILD_INTERVAL - optional, as days, defaults to 7
  * BUILD_TIME - optional, as days, defaults to 23:00:00 (UTC time)
  * USER_NAME - optional, username for nginx basic authentication
  * USER_PASS - optional, password for nginx basic authentication
  * SLACK_WEBHOOK_URL - optional, URL for a Slack webhook

This project contains a Dockerfile that builds a container that has a CRON-like shell script for running
zero_routing.py script. Additionally, nginx is running on the background and from container port 8080,
you can access the report generated by the script and the CSV files. These files are protected by
basic authentication.