<template>
<div class="container">
    <div class="page-header" style="padding-top:15px;padding-bottom:0px;margin-bottom:0px;">
        <p class="lead"><b>Pastamaker</b> pull requests dashboard</p>
    </div>
    <div style="margin-top:-50px;" class="pull-right">
        <input placeholder="travis token" style="height:1.5em;" type="password" v-model.lazy="travis_token" @change="save_travis_token()"/>
        <a href="#" @click="hide_all_tabs()"><span class="glyphicon glyphicon-circle-arrow-up"></span></a>
    </div>
    <div class="autorefresh">
        <i><small>
                <span>Updated <time am-time-ago="last_update"></time></span>
                <span v-if="autorefresh">
                    <span v-if="refreshing">, refreshing...</span>
                    <span v-if="!refreshing">, refresh in {{ counter }} seconds</span>
                </span>
                <span v-if="event">
                    by a push event
                </span>
                <span v-if="!(event || autorefresh)">
                    , autorefresh disabled
                </span>
                <span v-if="rq_default_count >= 0">, {{ rq_default_count }} github event<span v-if="rq_default_count > 1">s</span> pending</span>
            </small></i>
    </div>
    <Group v-for="group in groups"
           :key="group.owner + '/' + group.repo + '/' + group.branch"
           :group="group"
           :opened_travis_tabs="opened_travis_tabs"
           :opened_commits_tabs="opened_commits_tabs"
    ></Group>
</div>
</template>

<script>
import Group from './components/Group'

export default {
  name: 'Pastamaker',
  components: {
    Group
  },
  data () {
    return {
      'travis_token': null,
      'last_update': new Date(),
      'counter': 0,

      'groups': [],
      'opened_travis_tabs': {},
      'opened_commits_tabs': {},

      'refresh_interval': 5 * 60,
      'autorefresh': true,
      'refreshing': true,
      'event': false,
      'rq_default_count': 0
    }
  },
  methods: {
    toggle_info (pull, type) {
      var open = pull['open_' + type + '_row']
      this.close_info('commits')
      this.close_info('travis')
      if (!open) {
        this.open_info(type)
        if (type === 'travis') {
          if (['success', 'failure', 'error'].indexOf(pull.pastamaker_travis_state) === -1) {
            this.refresh_travis()
          }
        }
      }
    },
    open_info (pull, type) {
      var repo = pull.base.repo.full_name
      var tab = this['opened_' + type + '_tabs']
      if (!tab.hasOwnProperty(repo)) {
        tab[repo] = []
      }
      tab[repo].push(pull.number)
      pull['open_' + type + '_row'] = true
    },
    close_info (pull, type) {
      var repo = pull.base.repo.full_name
      var tab = this['opened_' + type + '_tabs']
      if (!tab.hasOwnProperty(repo)) {
        tab[repo] = []
      }
      tab[repo] = tab[repo].filter(e => e !== pull.number)
      pull['open_' + type + '_row'] = false
    },
    refresh_travis (pull) {
    }
  },
  events: {
    toggle_info (pull, type) {
      this.toggle_info(pull, type)
    },
    refresh_travis (pull) {
      if (!pull.pastamaker_travis_detail) {
        pull.pastamaker_travis_detail = {}
      }
      pull.pastamaker_travis_detail.refreshing = true

      var buildID = pull.pastamaker_travis_url.split('?')[0].split('/').slice(-1)[0]
      var V2Headers = { 'Accept': 'application/vnd.travis-ci.2.1+json' }
      var travisBaseUrl = 'https://api.travis-ci.org'
      fetch({
        'method': 'GET',
        'url': travisBaseUrl + '/builds/' + buildID,
        'headers': V2Headers
      }).then(response => {
        return response.json()
      }).then(data => {
        var countUpdatedJob = 0
        var build = data.build
        build.resume_state = pull.pastamaker_travis_state
        build.jobs = []
        build.refreshing = false
        build.job_ids.forEach((jobID) => {
          this.$http({
            'method': 'GET',
            'url': travisBaseUrl + '/jobs/' + jobID,
            'headers': V2Headers
          }).then((response) => {
            if (pull.pastamaker_travis_state === 'pending' && data.job.state === 'started') {
              build.resume_state = 'working'
            }
            build.jobs.push(data.job)
            countUpdatedJob += 1
            if (countUpdatedJob === build.job_ids.length) {
              pull.pastamaker_travis_detail = build
            }
          })
        })
      })
    }
  },
  created () {
    fetch('/status').then(response => {
      return response.json()
    }).then(data => {
      /*
      var old_tabs = {"travis": this.opened_travis_tabs,
                      "commits": this.opened_commits_tabs}
      this.opened_travis_tabs = {}
      this.opened_commits_tabs = {}
      */
      this.groups = data
      this.last_update = new Date()
      this.refreshing = false
      this.counter = this.refresh_interval
    })
  }
}
</script>
<style>
.hidden { display: none; }
.error {
    display: none;
    padding: 100px;
    color: red;
}
a.resolved { text-decoration: line-through !important; }
img.avatar {
    margin-right: 2px;
    margin-bottom: 2px;
    border-radius: 3px;
    width: 24px;
    height: 24px;
}
.count-comments {
    font-size: 80%;
}
.good {
    color: green;
}
.bad {
    color: red;
}
.maybe {
    color: orange;
}
.refreshing {
    color: #0099cc;
}

footer {
    font-size: 70%;
}
footer p {
    text-align: center;
}

table.expanded td {
    font-size: 80%;
}
.autorefresh {
    text-align: right;
    width: 100%;
    height: 20px;
    margin-top: -20px;
}
.label-as-badge {
    border-radius: 1em;
}
.group {
    margin-bottom: 5px;
}
.group table.table {
    margin-bottom: 15px;
}

a.closer {
    color: #999;
}
a.closer:hover {
    color: #333;
}

/* minimum widths needed when working with multiple tables */
table.multiple .last-updated {
    width: 110px;
}
table.multiple .reviews {
    padding-right: 3px;
    width: 65px;
}
table.multiple .milestone,
table.multiple .queue,
table.multiple .mergeable,
table.multiple .state {
    width: 35px;
    text-align: center;
}
table.multiple .state a {
    display: block;
    width: 100%;
}

p.table-foot-note {
    text-align: right;
    font-size: 80%;
}

.title a {
    font-weight: normal;
}
p.diff-stats {
    font-weight: bold;
    text-align: right;
    font-size: 80%;
    margin-right: 16px;
}
td.changes a {
    color: black;
}
td.labels strong {
    display: inline-block;
    padding: 3px 4px;
    font-size: 11px;
    font-weight: bold;
    line-height: 1;
    color: white;
    border-radius: 2px;
    box-shadow: 0px -1px 0px rgba(0, 0, 0, 0.12) inset;
}

/*
.comment-body {
    border-bottom: 1px solid #CCCCCC;
    margin-left: 30px;
    margin-bottom: 6px;
}
*/
.blinking {
    -webkit-animation-name: blinker;
    -webkit-animation-duration: 1s;
    -webkit-animation-timing-function: linear;
    -webkit-animation-iteration-count: infinite;

    -moz-animation-name: blinker;
    -moz-animation-duration: 1s;
    -moz-animation-timing-function: linear;
    -moz-animation-iteration-count: infinite;

    animation-name: blinker;
    animation-duration: 1s;
    animation-timing-function: linear;
    animation-iteration-count: infinite;
}
@-moz-keyframes blinker {
    0% { opacity: 1.0; }
    50% { opacity: 0.0; }
    100% { opacity: 1.0; }
}
@-webkit-keyframes blinker {
    0% { opacity: 1.0; }
    50% { opacity: 0.0; }
    100% { opacity: 1.0; }
}
@keyframes blinker {
    0% { opacity: 1.0; }
    50% { opacity: 0.0; }
    100% { opacity: 1.0; }
}

.bs-callout {
    padding: 10px 20px 5px 20px;
    margin: 0 0 20px 0;
    border: 1px solid #eee;
    border-left-width: 5px;
    border-radius: 3px;
}
.bs-callout h5 {
    margin-top: 0;
    margin-bottom: 5px;
}
.bs-callout p:last-child {
    margin-bottom: 0;
}
.bs-callout code {
    border-radius: 3px;
}
.bs-callout+.bs-callout {
    margin-top: -5px;
}
.bs-callout-default {
    border-left-color: #777;
}
.bs-callout-default h5 {
    color: #777;
}
.bs-callout-primary {
    border-left-color: #428bca;
}
.bs-callout-primary h5 {
    color: #428bca;
}
.bs-callout-success {
    border-left-color: #5cb85c;
}
.bs-callout-success h5 {
    color: #5cb85c;
}
.bs-callout-danger {
    border-left-color: #d9534f;
}
.bs-callout-danger h5 {
    color: #d9534f;
}
.bs-callout-warning {
    border-left-color: #f0ad4e;
}
.bs-callout-warning h5 {
    color: #f0ad4e;
}
.bs-callout-info {
    border-left-color: #5bc0de;
}
.bs-callout-info h5 {
    color: #5bc0de;
}
</style>
