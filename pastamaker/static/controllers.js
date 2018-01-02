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
        this.$scope.rq_default_count = -1;
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
            source.addEventListener("rq-refresh", (event) => {
                this.$scope.rq_default_count = event.data;
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
            this.$http({'method': 'GET', 'url': '/status'}).then((response) => {
                this.update_pull_requests(response.data);
            }).error(this.on_error);
        },
        update_pull_requests: function(data) {
            var old_tabs = {"travis": this.opened_travis_tabs,
                            "commits": this.opened_commits_tabs,
                            "comments": this.opened_comments_tabs}
            var comments_read_to_keep = [];
            this.opened_travis_tabs = {};
            this.opened_commits_tabs = {};
            this.opened_comments_tabs = {};
            this.$scope.groups = []
            data.forEach((group) => {

                var repo;

                group.pulls.forEach((pull) => {
                    repo = pull.base.repo.full_name;
                    ["travis", "commits", "comments"].forEach((type) => {
                        var tabs = old_tabs[type];
                        if (tabs.hasOwnProperty(repo) && tabs[repo].includes(pull.number)) {
                            this.open_info(pull, type);
                        }
                    });

                    // helper for filtered comments
                    var cache_key = this.get_comments_read_cache_key(pull)
                    pull.pastamaker_comments_filtered = this.filter_comments(pull.pastamaker_comments);
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
                    this.close_info(pull, "travis");
                    this.close_info(pull, "commits");
                    this.close_info(pull, "comments");
                });
            });
        },
        get_comments_read_cache_key: function(pull){
            return "comment~" + pull.base.repo.full_name + "~" + pull.number;
        },
        toggle_info: function(pull, type) {
            var open = pull["open_" + type + "_row"];
            this.close_info(pull, "commits");
            this.close_info(pull, "comments");
            this.close_info(pull, "travis");
            if (!open) {
                this.open_info(pull, type);

                if (type === "comments") {
                    pull.pastamaker_comments_read = pull.pastamaker_comments_filtered.length;
                    this.$window.localStorage.setItem(
                        this.get_comments_read_cache_key(pull),
                        pull.pastamaker_comments_read.toString()
                    );
                } else if (type === "comments") {
                    this.refresh_travis(pull);
                }
            }
        },
        open_info: function(pull, type) {
            var repo = pull.base.repo.full_name
            var tab = "opened_" + type + "_tabs";
            if (!this[tab].hasOwnProperty(repo)){
                this[tab][repo] = [];
            }
            this[tab][repo].push(pull.number)
            pull["open_" + type + "_row"] = true;
        },
        close_info: function(pull, type) {
            var repo = pull.base.repo.full_tab
            var tab = "opened_" + type + "_tabs";
            if (!this[tab].hasOwnProperty(repo)){
                this[tab][repo] = [];
            }
            this[tab][repo] = this[tab][repo].filter(e => e !== pull.number);
            pull["open_" + type + "_row"] = false;
        },
        refresh_travis: function(pull) {
            pull.pastamaker_travis_detail = undefined;
            var build_id = pull.pastamaker_travis_url.split("?")[0].split("/").slice(-1)[0];
            var v2_headers = { "Accept": "application/vnd.travis-ci.2+json" };
            var travis_base_url = 'https://api.travis-ci.org';
            this.$http({
                "method": "GET",
                "url": travis_base_url + "/builds/" + build_id,
                "headers": v2_headers,
            }).then((response) => {
                pull.pastamaker_travis_detail = response.data.build;
                pull.pastamaker_travis_detail.resume_state = pull.pastamaker_travis_state;
                pull.pastamaker_travis_detail.jobs = [];
                pull.pastamaker_travis_detail.job_ids.forEach((job_id) => {
                    this.$http({
                        "method": "GET",
                        "url": travis_base_url + "/jobs/" + job_id,
                        "headers": v2_headers,
                    }).then((response) => {
                        if (pull.pastamaker_travis_state == "pending" && response.data.job.state == "started") {
                            pull.pastamaker_travis_detail.resume_state = "working";
                        }
                        pull.pastamaker_travis_detail.jobs.push(response.data.job);
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
