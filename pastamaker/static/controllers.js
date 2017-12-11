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
        this.opened_comments_tabs = {};
        this.$scope.tabs_are_open = {};

        if(typeof(EventSource) !== "undefined") {
            console.log("event enabled");
            this.$scope.event = true;
            var source = new EventSource('/status/stream');
            source.addEventListener("ping", (event) => {
                // Just for testing the connection for heroku
            }, false);
            source.addEventListener("refresh", (event) => {
                this.update_pull_requests(JSON.parse(event.data));
                this.$scope.$apply()
            }, false);
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
            this.$http.get('/status').success((data, status, headers) => {
                this.update_pull_requests(data);
            }).error(this.on_error);
        },
        update_pull_requests: function(data) {

            var old_travis_tabs = this.opened_travis_tabs;
            var old_commits_tabs = this.opened_commits_tabs;
            var old_comments_tabs = this.opened_comments_tabs;
            var comments_read_to_keep = [];
            this.opened_travis_tabs = {};
            this.opened_commits_tabs = {};
            this.opened_comments_tabs = {};
            this.$scope.groups = []
            data.forEach((group) => {

                var repo;

                group.pulls.forEach((pull) => {
                    // reopen tabs
                    repo = pull.base.repo.full_name;
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
                    if (old_comments_tabs.hasOwnProperty(repo)){
                        if (old_comments_tabs[repo].indexOf(pull.number) !== -1) {
                            this.toggle_comments_info(pull);
                        }
                    }

                    // prepare filtred comments
                    pull.pastamaker_comments_filtered = this.filter_comments(pull.pastamaker_comments);

                    var cache_key = "comment~" + repo + "~" + pull.number;
                    pull.pastamaker_comments_read = this.$window.localStorage.getItem(cache_key);
                    if (pull.pastamaker_comments_read == null){
                        pull.pastamaker_comments_read = 0;
                    } else {
                        pull.pastamaker_comments_read = parseInt(pull.pastamaker_comments_read);
                    }
                    comments_read_to_keep.push(cache_key);
                });

                this.$scope.groups.push(group)
            });
            this.$scope.last_update = new Date();
            this.$scope.refreshing = false;
            this.$scope.counter = this.refresh_interval;

            for (var k in this.$window.localStorage) {
                if (!comments_read_to_keep.includes(k)) {
                    this.$window.localStorage.removeItem(k);
                }
            }
        },
        on_error: function(data, status) {
            console.warn(data, status);
            this.$scope.refreshing = false;
            this.$scope.counter = this.refresh_interval;
        },
        hide_all_tabs: function() {
            this.$scope.groups.forEach((group) => {
                group.pulls.forEach((pull) => {
                    var repo = pull.base.repo.full_name;
                    pull.open_travis_row = false;
                    if (this.opened_travis_tabs.hasOwnProperty(repo)){
                        this.opened_travis_tabs[repo] = this.opened_travis_tabs[repo].filter(e => e !== pull.number)
                    }
                    pull.open_commits_row = false;
                    if (this.opened_commits_tabs.hasOwnProperty(repo)){
                        this.opened_commits_tabs[repo] = this.opened_commits_tabs[repo].filter(e => e !== pull.number)
                    }
                    pull.open_comments_row = false;
                    if (this.opened_comments_tabs.hasOwnProperty(repo)){
                        this.opened_comments_tabs[repo] = this.opened_comments_tabs[repo].filter(e => e !== pull.number)
                    }
                });
            });
        },
        toggle_comments_info: function(pull) {
            var opened = pull.open_comments_row;
            var repo = pull.base.repo.full_name;
            var cache_key = "comment~" + repo + "~" + pull.number;
            if (!opened) {
                if (!this.opened_comments_tabs.hasOwnProperty(repo)){
                    this.opened_comments_tabs[repo] = [];
                }
                this.opened_comments_tabs[repo].push(pull.number);
                pull.open_comments_row = true;
                pull.pastamaker_comments_read = pull.pastamaker_comments_filtered.length;
                this.$window.localStorage.setItem(cache_key, pull.pastamaker_comments_read.toString());
            } else {
                pull.open_comments_row = false;
                this.opened_comments_tabs[repo] = this.opened_comments_tabs[repo].filter(e => e !== pull.number)
            }
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
            ).success((data, status, headers) => {
                pull.pastamaker_travis_detail = data.build;
                pull.pastamaker_travis_detail.resume_state = pull.pastamaker_travis_state;
                pull.pastamaker_travis_detail.jobs = [];
                data.build.job_ids.forEach((job_id) => {
                    this.$http.get(travis_base_url + "/jobs/" + job_id,
                                   {headers: v2_headers}
                    ).success(function(data, status, headers) {
                        if (pull.pastamaker_travis_state == "pending" && data.job.state == "started") {
                            pull.pastamaker_travis_detail.resume_state = "working";
                        }
                        pull.pastamaker_travis_detail.jobs.push(data.job);
                    });
                })
            });
        },
        open_all_commits: function(pull){
            pull.pastamaker_commits.forEach((commit) => {
                var url = "https://github.com/" + pull.base.repo.full_name +
                    "/pull/" + pull.number + "/commits/" + commit.sha;
                this.$window.open(url, commit.sha);
            });
        },
        JobSorter: function(job){
            return parseInt(job.number.replace(".", ""));
        },
        filter_comments: function(comments) {
            var filtered_comments = []
            comments.forEach((comment) => {
                if (!comment.body.startsWith("Pull-request updated, HEAD is now")
                    && comment.user.login !== "pastamaker[bot]"
                    && comment.state === "COMMENT") {
                    filtered_comments.push(comment)
                }
            });
            return filtered_comments;
        }
    },
});

app.filter("GetCommitTitle", function(){
    return function(commit) {
        return commit.commit.message.split("\n")[0];
    }
});

app.filter("SelectLines", function(){
    return function(text, pos, len) {
        var lines = text.split("\n");
        lines =  lines.slice(pos-len, pos+len)
        if (lines.length <= 0){
            return text;
        } else {
            return lines.join("\n");
        }
    }
});
