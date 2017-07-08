web: gunicorn pastamaker.wsgi --log-file - --capture-output --preload -k gevent -w 4
worker: python pastamaker/worker.py
