==========
pastamaker
==========

.. image:: https://travis-ci.org/sileht/pastamaker.png?branch=master
    :target: https://travis-ci.org/sileht/pastamaker
    :alt: Build Status

pastamaker is a Github App to automatically manage Pull Requests
"branch update" and "merge" when this one have 2 reviewer approvals

Anything catchng "@pastamaker.*fast merge" will bypass the required approvals.

It's currently used by `gnocchixyz projects <https://github.com/gnocchixyz>`_, the app name is 'pastamaker'.

Github App Settings
===================

You should obviously replace https://<app-name>.herokuapp.com by the url where you host the application.

General
-------

* Homepage URL:  https://<app-name>.herokuapp.com
* User authorization callback URL: https://<app-name>.herokuapp.com/auth
* Setup URL: None
* Webhook URL: https://<app-name>.herokuapp.com/event
* Webhook secret: <webhook_secret>
* Generate the private key: # Click on the button #

Pick the ID on the right, you will need it later.

Permissions
-----------

::

    Commit statuses - ReadOnly

      [x] Status

    Pull requests - ReadWrite

      [x] Pull request
      [x] Pull request review
      [x] Pull request review comment

    Repository contents - ReadWrite

      No webook


Heroku Setup
============

.. code-block:: shell

    heroku apps:create <app-name>
    heroku addons:create redistogo:nano
    heroku addons:create scheduler:standard

    heroku config:set -a <app-name> \
        PASTAMAKER_INTEGRATION_ID=XXXX \
        PASTAMAKER_WEBHOOK_SECRET="<webhook_secret>" \
        PASTAMAKER_PRIVATE_KEY="$(cat <path to the private key>)" \
        PASTAMAKER_BASE_URL="https://<app-name>.herokuapp.com" \
        PASTAMAKER_WEBHACK_USERNAME="<app-name>-bot" \
        PASTAMAKER_WEBHACK_PASSWORD="<password>"

    git push -f heroku master

    heroku ps:scale worker=1

    heroku addons:open scheduler:standard
    # trigger refresh manually or to configure the scheduler
    heroku run python pastamaker/refresher.py YYYYY/gnocchixyz/gnocchi/branch
