/* Controllers */

var app = angular.module('triage.controllers', ['classy']);

app.classy.controller({
    name: 'AppController',
});

app.classy.controller({
    name: 'PullsController',
    inject: ['$scope', '$http', '$interval', '$location'],
    init: function() {
        'use strict';
        this.refresh_interval = 5 * 60;

        this.$scope.counter = 0;
        this.$scope.autorefresh = false;
        this.$scope.event = false;

        if (this.$location.search().event === "true"){
            console.log("event enabled");
            this.$scope.event = true;
            var source = new EventSource('/status/stream');
            source.addEventListener("ping", function(event) {
                // Just for testing the connection for heroku
            }, false);
            source.addEventListener("refresh", function(event) {
                this.update_pull_requests(JSON.parse(event.data));
                this.$scope.$apply()
            }.bind(this), false);
        } else {
            this.refresh();
            if (this.$location.search().autorefresh === "true"){
                console.log("auto refresh enabled");
                this.$scope.autorefresh = true;
                this.$interval(this.count, 1 * 1000);
                this.$interval(this.refresh, this.refresh_interval * 1000);
            }
        }
    },
    count: function(){
        this.$scope.counter -= 1;
    },
    refresh: function() {
        console.log("refreshing");
        this.$scope.refreshing = true;
        this.$http.get('/status').success(function(data, status, headers) {
            this.update_pull_requests(data);
        }.bind(this)).error(this.on_error);
    },
    update_pull_requests: function(data) {
        this.$scope.groups = [];
        data.forEach(function(group) {
            this.$scope.groups.push(group)
        }.bind(this));
        this.$scope.last_update = new Date();
        this.$scope.refreshing = false;
        this.$scope.counter = this.refresh_interval;
    },
    on_error: function(data, status) {
        console.warn(data, status);
        this.$scope.refreshing = false;
        this.$scope.counter = this.refresh_interval;
    },
})
;
