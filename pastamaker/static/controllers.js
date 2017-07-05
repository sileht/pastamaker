/* Controllers */

var app = angular.module('triage.controllers', ['classy']);

app.classy.controller({
    name: 'AppController',
});

app.classy.controller({
    name: 'PullsController',
    inject: ['$scope', '$http'],
    init: function() {
        'use strict';

        this.$scope.groups = [];
        this.$http.get('/status').success(function(data, status, headers) {
            data.forEach(function(group) {
                this.$scope.groups.push(group)
            }.bind(this));
        }.bind(this))
        .error(function(data, status) {
            console.warn(data, status);
        });
    },
})
;
