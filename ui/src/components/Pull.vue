<template>
    <tr>
        <td class="title">
            <div class="pull-right"><span style="color:green">+{{ additions }}</span> / <span style="color:red">-{{ deletions }}</span></div>
            <a :href="user.html_url"><img :src="user.avatar_url" class="avatar" :alt="user.login"></a>
            <a href="#" @click="toggle_info('commits')" style="display:inline-block;padding-left:5px;">
                <span :class="{'glyphicon glyphicon-circle-arrow-down': open_commits_row, 'glyphicon glyphicon-circle-arrow-right': !open_commits_row}"></span>
            </a>
            <a :href="html_url" target="_blank">{{ title }} <span style="color:grey">#{{ number }}</span></a>
        </td>
        <td class="state"><a :href="html_url" target="_blank">{{ comments }}</a></td>
        <td class="state"><a :href="commits_url" target="_blank">{{ commits }}</a></td>
        <td class="state"><a :href="files_url" target="_blank">{{ changed_files }}</a></td>
        <td class="last-updated"><time am-time-ago="updated_at"></time></td>
        <td class="state" v-if="pastamaker_travis_detail != null">
            <a href="#" @click="toggle_info('travis')" v-show="pastamaker_travis_detail.refreshing != true">
                <span v-if="pastamaker_travis_detail.resume_state == 'success'" title="Last test succeeded" class="good glyphicon glyphicon-ok"></span>
                <span v-if="pastamaker_travis_detail.resume_state == 'failure'" title="Last test failed!" class="bad glyphicon glyphicon-remove"></span>
                <span v-if="pastamaker_travis_detail.resume_state == 'error'" title="Last test error!" class="bad glyphicon glyphicon-remove"></span>
                <span v-if="pastamaker_travis_detail.resume_state == 'pending'" title="Latest test pending" class="maybe glyphicon glyphicon-time"></span>
                <span v-if="pastamaker_travis_detail.resume_state == 'working'" title="Latest test pending" class="maybe glyphicon glyphicon-cog"></span>
                <span v-if="pastamaker_travis_detail.resume_state == 'unknown'" title="Latest test unknown" class="maybe glyphicon glyphicon-question-sign"></span>
            </a>
            <span v-if="pastamaker_travis_detail.refreshing == true" class="refreshing glyphicon glyphicon-cloud-download"></span>
        </td>
        <td class="state" v-if="pastamaker_travis_detail == null">
            <a href="#" @click="toggle_info('travis')">
                <span v-if="pastamaker_travis_state == 'success'" title="Last test succeeded" class="good glyphicon glyphicon-ok"></span>
                <span v-if="pastamaker_travis_state == 'failure'" title="Last test failed!" class="bad glyphicon glyphicon-remove"></span>
                <span v-if="pastamaker_travis_state == 'error'" title="Last test error!" class="bad glyphicon glyphicon-remove"></span>
                <span v-if="pastamaker_travis_state == 'pending'" title="Latest test pending" class="maybe glyphicon glyphicon-time"></span>
                <span v-if="pastamaker_travis_state == 'working'" title="Latest test pending" class="maybe glyphicon glyphicon-cog"></span>
                <span v-if="pastamaker_travis_state == 'unknown'" title="Latest test unknown" class="maybe glyphicon glyphicon-question-sign"></span>
            </a>
        </td>
        <td class="mergeable">
            <span v-if="mergeable == true" :title="mergeable_state" class="good glyphicon glyphicon-ok"></span>
            <span v-if="mergeable == false" :title="mergeable_state" class="bad glyphicon glyphicon-remove"></span>
            <span v-if="mergeable == null" :title="mergeable_state" class="bad glyphicon glyphicon-question-sign"></span>
        </td>
        <td class="milestone">
            <a v-if="milestone" :href="milestone.html_url" target="_blank">{{ milestone.title }}</a>
        </td>
        <td class="reviews info">
            <a v-for="user in pastamaker_approvals[0]"
               :key="user.login"
               :href="user.html_url"
               :title="user.login"
               target="_blank">
                <img :src="user.avatar_url" class="avatar" :alt="user.login">
            </a>
            <span v-for="n in pastamaker_approvals[3]" v-bind:key="n">
                <img class="avatar" style="border:1px dashed white; background-color: #e2f1f9;" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA"/>
            </span>
        </td>
        <td class="reviews warning">
            <a v-for="user in pastamaker_approvals[1]"
               :key="user.login"
               :href="user.html_url"
               :title="user.login"
               target="_blank"><img :src="user.avatar_url" class="avatar" :alt="user.login"></a>
        </td>
        <td class="queue" :class="{success: pastamaker_weight >= 10, active: pastamaker_weight == -1, info: pastamaker_weight >= 0 && pastamaker_weight < 10}">
            <span v-if="pastamaker_weight >= 0">{{ pastamaker_weight }}</span>
            <span v-if="pastamaker_weight < 0">N/A</span>
        </td>
    </tr>
</template>

<script>
export default {
  name: 'Pull',
  props: ['pull'],
  methods: {
    toggle_info (type) {
      this.$parent.$parent.toggle_info(this.pull, type)
    }
  },
  created () {
    if (this.pull.pastamaker_travis_state === 'pending') {
      this.$parent.$parent.refresh_travis(this.pull)
    }
    /*
    var repo = this.pull.base.repo.full_name
    ['travis', 'commits'].forEach(type => {
      var tabs = this.$root.$data['opened_' + type + '_tabs']
      if (tabs.hasOwnProperty(repo) && tabs[repo].includes(this.pull.number)) {
        this.open_info(type)
      }
    })
    */
  },
  data () {
    return this._.merge(this.pull, {
      'open_commits_row': this.pull.open_commits_row,
      'open_travis_row': this.pull.open_travis_row,
      'files_url': this.pull.html_url + '/files',
      'commits_url': this.pull.html_url + '/commits'
    })
  }
}
</script>
