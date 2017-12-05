/* Controllers */

var app = angular.module('triage.controllers', ['classy']);

app.classy.controller({
    name: 'AppController',
});

app.classy.controller({
    name: 'PullsController',
    inject: ['$scope', '$http', '$interval', '$location', '$window'],
    init: function() {
        'use strict';
        this.refresh_interval = 5 * 60;

        this.$scope.counter = 0;
        this.$scope.autorefresh = false;
        this.$scope.event = false;
        this.opened_travis_tabs = {};
        this.opened_commits_tabs = {};
        this.$scope.tabs_are_open = {};

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
    methods: {
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
            var old_travis_tabs = this.opened_travis_tabs;
            var old_commits_tabs = this.opened_commits_tabs;
            this.opened_travis_tabs = {};
            this.opened_commits_tabs = {};
            this.$scope.groups = []
            data.forEach(function(group) {

                // reopen tabs
                group.pulls.forEach(function(pull) {
                    var repo = pull.base.repo.full_name;
                    if (old_travis_tabs.hasOwnProperty(repo)){
                        if (old_travis_tabs[repo].indexOf(pull.number) !== -1) {
                            this.toggle_travis_info(pull);
                        }
                    }
                    if (old_commits_tabs.hasOwnProperty(repo)){
                        if (old_commits_tabs[repo].indexOf(pull.number) !== -1) {
                            this.toggle_commits_info(pull);
                        }
                    }
                }.bind(this));

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
        hide_all_tabs: function() {
            this.$scope.groups.forEach(function(group) {
                group.pulls.forEach(function(pull) {
                    var repo = pull.base.repo.full_name;
                    pull.open_travis_row = false;
                    if (this.opened_travis_tabs.hasOwnProperty(repo)){
                        this.opened_travis_tabs[repo] = this.opened_travis_tabs[repo].filter(e => e !== pull.number)
                    }
                    pull.open_commits_row = false;
                    if (this.opened_commits_tabs.hasOwnProperty(repo)){
                        this.opened_commits_tabs[repo] = this.opened_commits_tabs[repo].filter(e => e !== pull.number)
                    }
                }.bind(this));
            }.bind(this));
        },
        toggle_commits_info: function(pull) {
            var opened = pull.open_commits_row;
            var repo = pull.base.repo.full_name;
            if (!opened) {
                if (!this.opened_commits_tabs.hasOwnProperty(repo)){
                    this.opened_commits_tabs[repo] = [];
                }
                this.opened_commits_tabs[repo].push(pull.number);
                pull.open_commits_row = true;
            } else {
                pull.open_commits_row = false;
                this.opened_commits_tabs[repo] = this.opened_commits_tabs[repo].filter(e => e !== pull.number)
            }
        },
        toggle_travis_info: function(pull) {
            var opened = pull.open_travis_row;
            var repo = pull.base.repo.full_name
            if (!opened) {
                if (!this.opened_travis_tabs.hasOwnProperty(repo)){
                    this.opened_travis_tabs[repo] = [];
                }
                this.opened_travis_tabs[repo].push(pull.number);
                pull.open_travis_row = true;
                // this.refresh_travis(pull);
            } else {
                pull.open_travis_row = false;
                this.opened_travis_tabs[repo] = this.opened_travis_tabs[repo].filter(e => e !== pull.number)
            }
        },
        refresh_travis: function(pull) {
            pull.pastamaker_travis_detail = undefined;
            var build_id = pull.pastamaker_travis_url.split("?")[0].split("/").slice(-1)[0];
            var v2_headers = { "Accept": "application/vnd.travis-ci.2+json" };
            var travis_base_url = 'https://api.travis-ci.org'
            this.$http.get(travis_base_url + "/builds/" + build_id,
                           {headers: v2_headers}
            ).success(function(data, status, headers) {
                pull.pastamaker_travis_detail = data.build;
                pull.pastamaker_travis_detail.resume_state = pull.pastamaker_travis_state;
                pull.pastamaker_travis_detail.jobs = [];
                data.build.job_ids.forEach(function(job_id) {
                    this.$http.get(travis_base_url + "/jobs/" + job_id,
                                   {headers: v2_headers}
                    ).success(function(data, status, headers) {
                        if (pull.pastamaker_travis_state == "pending" && data.job.state == "started") {
                            pull.pastamaker_travis_detail.resume_state = "working";
                        }
                        pull.pastamaker_travis_detail.jobs.push(data.job);
                    }.bind(this));
                }.bind(this))
            }.bind(this));
        },
        open_all_commits: function(pull){
            pull.pastamaker_commits.forEach(function(commit) {
                var url = "https://github.com/" + pull.base.repo.full_name +
                    "/pull/" + pull.number + "/commits/" + commit.sha;
                this.$window.open(url, commit.sha);
            }.bind(this));
        },
        JobSorter: function(job){
            return parseInt(job.number.replace(".", ""));
        },
    },
});

app.filter("GetCommitTitle", function(){
    return function(commit) {
        return commit.commit.message.split("\n")[0];
    }
});
