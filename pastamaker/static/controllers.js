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
        this.$scope.current_travis_raw_open = null;

        if(typeof(EventSource) !== "undefined") {
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
        if (this.$scope.current_travis_raw_open) {
            this.toggle_travis_info(this.$scope.current_travis_raw_open);
        }
    },
    on_error: function(data, status) {
        console.warn(data, status);
        this.$scope.refreshing = false;
        this.$scope.counter = this.refresh_interval;
    },
    hide_all_travis_info: function() {
        this.$scope.groups.forEach(function(group) {
            group.pulls.forEach(function(pull) {
                pull.open_travis_row = false;
            });
        });
    },
    toggle_travis_info: function(pull) {
        var opened = pull.open_travis_row;
        this.hide_all_travis_info()
        if (!opened) {
            pull.open_travis_row = true;
            this.$scope.current_travis_raw_open = pull;
            this.refresh_travis(pull);
        } else {
            this.$scope.current_travis_raw_open = null;
        }
    },
    refresh_travis: function(pull) {
        pull.travis_build = undefined;
        pull.travis_jobs = [];
        var build_id = pull.travis_url.split("?")[0].split("/").slice(-1)[0];
        var v2_headers = { "Accept": "application/vnd.travis-ci.2+json" };
        var travis_base_url = 'https://api.travis-ci.org'
        this.$http.get(travis_base_url + "/builds/" + build_id,
                       {headers: v2_headers}
        ).success(function(data, status, headers) {
            pull.travis_build = data.build;
            pull.travis_jobs = [];
            data.build.job_ids.forEach(function(job_id) {
                this.$http.get(travis_base_url + "/jobs/" + job_id,
                               {headers: v2_headers}
                ).success(function(data, status, headers) {
                    pull.travis_jobs.push(data.job);
                }.bind(this));
            }.bind(this))
        }.bind(this));
    },
    JobSorter: function(job){
        return parseInt(job.number.replace(".", ""));
    },
})
;
