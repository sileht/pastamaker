web: newrelic-admin run-program gunicorn pastamaker.wsgi --log-file - --capture-output -k gevent -w 4 --timeout 60
worker: newrelic-admin run-program python pastamaker/worker.py
