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
        this.$scope.counter = 0;
        this.refresh()
        this.$scope.autorefresh = this.$location.search().autorefresh === "true";
        if (this.$scope.autorefresh){
            console.log("auto refresh enabled");
            this.$interval(this.refresh, 60 * 1000);
            this.$interval(this.count, 1 * 1000);
        }
        return
        if (typeof(EventSource) !== "undefined") {
            var source = new EventSource('/status/stream');
            source.onmessage = function (event) {
                var data = JSON.parse(event.data);
                this.$scope.groups = [];
                data.forEach(function(group) {
                    this.$scope.groups.push(group)
                }.bind(this));
            }.bind(this);
        } else {
            console.warn("No EventSource support, disabling auto refresh");
            this.refresh()
        }
    },
    count: function(){
        this.$scope.counter -= 1;
        console.log("count " + this.$scope.counter);
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
            this.$scope.counter = 60;
        }.bind(this))
        .error(function(data, status) {
            console.warn(data, status);
            this.$scope.refreshing = false;
            this.$scope.counter = 60;
        });
    },
})
;
