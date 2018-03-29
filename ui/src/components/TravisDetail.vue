<template>
    <tr v-if="open_travis_row">
        <td colspan="11">
            <a href="#" class="pull-right" @click="toggle_info('travis')"><span class="glyphicon glyphicon-remove"></span></a>
            <a href="#" class="pull-right" style="margin-right:5px" @click="refresh_travis()"><span class="glyphicon glyphicon-refresh"></span></a>
            <a :href="pastamaker_travis_url" target="_blank" :title="pastamaker_travis_detail.state">
                <span v-if="pastamaker_travis_detail.refreshing == true" class="refreshing glyphicon glyphicon-cloud-download"></span>
                <span v-if="pastamaker_travis_detail.refreshing != true">
                    <span v-if="pastamaker_travis_detail.resume_state == 'success'" title="Last test succeeded" class="good glyphicon glyphicon-ok"></span>
                    <span v-if="pastamaker_travis_detail.resume_state == 'failure'" title="Last test failed!" class="bad glyphicon glyphicon-remove"></span>
                    <span v-if="pastamaker_travis_detail.resume_state == 'error'" title="Last test error!" class="bad glyphicon glyphicon-remove"></span>
                    <span v-if="pastamaker_travis_detail.resume_state == 'pending'" title="Latest test pending" class="maybe glyphicon glyphicon-time"></span>
                    <span v-if="pastamaker_travis_detail.resume_state == 'working'" title="Latest test pending" class="maybe glyphicon glyphicon-cog"></span>
                    <span v-if="pastamaker_travis_detail.resume_state == 'unknown'" title="Latest test unknown" class="maybe glyphicon glyphicon-question-sign"></span>
                </span>
            </a>
            <a :href="pastamaker_travis_url" target="_blank" :title="pastamaker_travis_detail.state">
                <strong style="display:inline-block; width: 67px" :class="{maybe: ['pending', 'unknown'].indexOf(pastamaker_travis_state) !== -1, good: pastamaker_travis_state == 'success', bad: ['failure', 'error'].indexOf(pastamaker_travis_state) !== -1}">#{{ pastamaker_travis_detail.number }}</strong>
                <i>{{ pastamaker_travis_detail.job_ids.length }} jobs started <time am-time-ago="pastamaker_travis_detail.started_at"></time></i>
            </a>
            <TravisDetailJob v-for="job in pastamaker_travis_detail.job"
                             :key="job"
                             :job="job"
                             :pull="pull"
            ></TravisDetailJob>
         </td>
    </tr>
</template>

<script>
import TravisDetailJob from './TravisDetailJob.vue'

export default {
  name: 'TravisDetail',
  props: ['pull'],
  components: {
    TravisDetailJob
  },
  methods: {
    toggle_info (type) {
      this.$dispatch('toggle_info', this.pull, type)
    },
    refresh_travis () {
      this.$dispatch('refresh_travis', this.pull)
    }
  },
  data () {
    return this._.merge(this.pull, {})
  }
}
</script>
