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
        this.$scope.autorefresh = false;
        this.$scope.event = false;
        this.$scope.counter = 0;
        if (this.$location.search().event === "true"){
            this.$scope.event = true;
            var source = new EventSource('/status/stream');
            source.onmessage = function (event) {
                var data = JSON.parse(event.data);
                this.$scope.groups = [];
                data.forEach(function(group) {
                    this.$scope.groups.push(group)
                }.bind(this));
            }.bind(this);
        } else {
            this.refresh();
            if (this.$location.search().autorefresh === "true"){
                this.$scope.autorefresh = true;
                console.log("auto refresh enabled");
                this.$interval(this.refresh, this.refresh_interval * 1000);
                this.$interval(this.count, 1 * 1000);
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
            this.$scope.groups = [];
            data.forEach(function(group) {
                this.$scope.groups.push(group)
            }.bind(this));
            this.$scope.refreshing = false;
            this.$scope.counter = this.refresh_interval;
        }.bind(this))
        .error(function(data, status) {
            console.warn(data, status);
            this.$scope.refreshing = false;
            this.$scope.counter = this.refresh_interval;
        });
    },
})
;
