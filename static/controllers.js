/* Utility functions */

function truncate(s, l) {
    if (s.length > l) {
        return s.substring(0, l).trim() + '...';
    }
    return s;
}

 function pySplit(str, sep, num) {
    var pieces = str.split(sep);
    if (arguments.length < 3) {
        return pieces;
    }
    if (pieces.length < num) {
        return pieces;
    }
    return pieces.slice(0, num).concat(pieces.slice(num).join(sep));
 }



/* Controllers */

var app = angular.module('triage.controllers', ['classy']);

app.classy.controller({
    name: 'AppController',
    inject: ['$scope', '$q', '$http', '$location'],
    init: function() {}
});

app.classy.controller({
    name: 'PullsController',
    inject: ['$scope', '$q', '$http', '$routeParams', '$location', 'gobacker'],
    init: function() {
        'use strict';

        this.nanobar = new Nanobar();
        this.nanobar_level = 0;

        this.$http.get('/status')
        .success(function(data, status, headers) {
            data._data.forEach(function(group) {
                this.$scope.groups.push(group)
            });

        });

    },

    _startLoading: function() {
        this.$scope.loading = true;
        this.$scope.groups = [];
        // there are 5 requests we need to make per project
        this.$scope.owners.forEach(function(owner, i) {
            var group = {
                owner: owner,
                repo: this.$scope.repos[i],
                loading: true,
                pulls: []
            };
            this.loadPulls(group, 100 / this.$scope.owners.length);
            this.$scope.groups.push(group);
        }, this);
    },

    submitForm: function() {
        var repos = [];
        var new_owner = this.$.new_owner.trim();
        this.$.new_repos.split(',').forEach(function(repo) {
            this.$scope.owners.push(new_owner);
            this.$scope.repos.push(repo.trim());
        }, this);

        this.$location.path(this._newPath(this.$scope.owners, this.$scope.repos));
    },

    _getUserRepos: function(username, callback) {
        // See https://github.com/peterbe/github-pr-triage/issues/23
        var filter_event_types = [
            'PullRequestReviewCommentEvent',
            'PullRequestEvent',
            'IssueCommentEvent',
        ];
        this.$http
        .get('/githubproxy/users/' + username + '/events')
        .success(function(data) {
            var events = data._data;
            var repos_set = {};
            events.forEach(function(item, i) {
                if (filter_event_types.indexOf(item.type) > -1) {
                    if (item.type === 'IssueCommentEvent') {
                        // To GitHub a pull request is an issue.
                        // If you make a general comment on a PR it's the same
                        // as if you had made a comment on an issue.
                        // The only way to distinguish these two is to look at
                        // the html_url :(
                        if (item.payload.comment.html_url.indexOf('/issues/') > -1) {
                            // then it's just an issue comment on a regular issue
                            return;
                        }
                    }
                    repos_set[item.repo.name] = 1;
                }
            });
            var owners = [];
            var repos = [];
            for (var name in repos_set) {
                var combo = pySplit(name, '/', 1);
                owners.push(combo[0]);
                repos.push(combo[1]);
            }
            callback(owners, repos);
        }.bind(this))
        .error(function(data, status) {
            console.warn(data, status);
        });
    },

    _newPath: function(owners, repos) {
        var path = '/';
        var prev_owner = null;
        owners.forEach(function(owner, i) {
            if (prev_owner != owner) {
                if (prev_owner !== null) {
                    path += ';';
                }
                path += owner + ':';
            } else {
                path += ',';
            }
            path += repos[i];
            prev_owner = owner;
        });
        return path;
    },

    removeGroup: function(owner, repo) {
        var new_owners = [], new_repos = [];
        this.$scope.owners.forEach(function(each_owner, i) {
            if (!(each_owner === owner && this.$scope.repos[i] === repo)) {
                new_owners.push(each_owner);
                new_repos.push(this.$scope.repos[i]);
            }
        }, this);
        this.$location.path(this._newPath(new_owners, new_repos));
    },

    toggleExpandPull: function(pull) {
        if (!pull._expanded) {
            pull._events = this.$scope.getEvents(pull);
        }
        pull._expanded = !pull._expanded;
    },

    getEvents: function(pull) {
        var events = [];

        _.each(pull._commits || [], function(commit) {
            // console.dir(commit);
            events.push({
                _type: 'commit',
                _url: commit.html_url,
                _summary: truncate(commit.commit.message, 80),
                _date: commit.commit.author.date
            });
        });
        _.each(pull._statuses || [], function(status) {
            //console.dir(status);
            events.push({
                _type: 'status-' + status.state,
                _url: status.target_url,
                _summary: status.description,
                _date: status.created_at
            });
        });
        _.each(pull._comments || [], function(comment) {
            //console.dir(comment);
            events.push({
                _type: 'comment',
                _summary: '(by @' + comment.user.login +') ' + truncate(comment.body, 80),
                _url: comment.html_url,
                _date: comment.created_at
            });
        });
        //console.dir(events);
        //return [];
        return events;
    },

    getStatuses: function(pull) {
        return pull._statuses || [];
    },

    hasStatuses: function(pull) {
        return pull._statuses && pull._statuses.length;
    },

    isLastStatus: function(pull, state) {
        var last = this.$scope.lastStatus(pull);
        return last.state === state;
    },

    lastStatus: function(pull) {
        var statuses = pull._statuses || [];
        return statuses[0];  // confusing, I know
    },

    loadStatuses: function(pull, callback) {
        this.$http
        .get('/githubproxy/' + pull.statuses_url)
        .success(function(data) {
            pull._statuses = data._data;
        }.bind(this))
        .error(function(data, status) {
            console.warn(data, status);
        })
        .finally(function() {
            if (callback) callback();
        });
    },

    loadReviews: function(pull, callback) {
        this.$http
        .get('/githubproxy/' + pull.url + '/reviews')
        .success(function(data) {
            pull.reviews_ok = [];
            pull.reviews_ko = [];
            data._data.forEach(function(review) {
                if (review.state === "APPROVED") {
                    pull.reviews_ok = pull.reviews_ok.filter(function(user) {
                        return user.login != review.user.login;
                    });
                    pull.reviews_ko = pull.reviews_ko.filter(function(user) {
                        return user.login != review.user.login;
                    });

                    pull.reviews_ok.push(review.user);
                } else if (review.state === "DISMISSED" || review.state === "CHANGES_REQUESTED") {
                    pull.reviews_ok = pull.reviews_ok.filter(function(user) {
                        return user.login != review.user.login;
                    });
                    if (review.state === "CHANGES_REQUESTED") {
                        pull.reviews_ko = pull.reviews_ko.filter(function(user) {
                            return user.login != review.user.login;
                        });
                        pull.reviews_ko.push(review.user);
                    }
                }
            }, this);
        }.bind(this))
        .error(function(data, status) {
            console.warn(data, status);
        })
        .finally(function() {
            if (callback) callback();
        });
    },

    loadPulls: function(group, base_increment) {
        this.$http
        .get('/status')
        .success(function(data, status, headers) {
            //console.dir(data);
            var pulls = [];
            // To work out the increments for the nanobar, start with assuming
            // this group has 1 things it needs to do per pull request
            var increment = null;
            if (data._data.length) {
                increment = base_increment / (data._data.length * 1);
            } else {
                this.nanobarIncrement(base_increment);
            }
            var branches = []
            data._data.forEach(function(pull) {
                if (!branches.includes(pull.base.ref)){
                    branches.push(pull.base.ref);
                }
            });
            var queues = [];
            var queries = [];
            branches.forEach(function(branch) {
                queries.push(this.$http.get("/pastamakerproxy/queue/" + group.owner + "/" + group.repo + "/" + branch)
                .success(function(data, status, headers) {
                    queues[branch] = data._data.map(function(pull) {
                        return pull.number
                    });
                }.bind(this)));
            }, this);

            this.$q.all(queries).then(function(ret) {
                data._data.forEach(function(pull) {
                    //console.warn(pull);
                    pulls.push(pull);
                    var queue = queues[pull.base.ref];
                    if (queue !== undefined){
                        pull.queue_position = queue.indexOf(pull.number);
                    } else {
                        pull.queue_position = -1;
                    }
                    if (pull.queue_position < 0) {
                        pull.queue_position = "";
                    }
                    this.loadStatuses(pull, function() {
                        this.nanobarIncrement(increment);
                        this.loadReviews(pull, function() {
                            this.nanobarIncrement(increment);
                        });
                    }.bind(this));
                }, this);
                group.pulls = pulls;
                group.loading = false;
            }.bind(this));
        }.bind(this))
    },

    nanobarIncrement: function(increment) {
        if (this.nanobar_level >= 100) {
            console.log('> 100');
            return;
        }
        this.nanobar_level += increment;
        this.nanobar.go(Math.min(100, Math.ceil(this.nanobar_level)));
    },

    rememberWhereFrom: function() {
        this.gobacker.remember(this.$location.path());
    }

})
;
