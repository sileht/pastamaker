<template>
    <div :title="job_state" style="padding-left: 7px">
        <span v-if="refreshing == true" class="refreshing glyphicon glyphicon-cloud-download"></span>
        <span v-if="refreshing != true">
            <span v-if="state == 'received'" class="maybe glyphicon glyphicon-option-horizontal"></span>
            <span v-if="state == 'queued'" class="maybe glyphicon glyphicon-option-horizontal"></span>
            <span v-if="state == 'started'" class="maybe glyphicon glyphicon-cog"></span>
            <span v-if="state == 'created'"  class="maybe glyphicon glyphicon-time"></span>
            <span v-if="state == 'passed'" class="good glyphicon glyphicon-ok"></span>
            <span v-if="state == 'errored'" class="bad glyphicon glyphicon-remove"></span>
            <span v-if="state == 'failed'" class="bad glyphicon glyphicon-remove"></span>
        </span>
        <strong style="display:inline-block; width: 60px" :class="{maybe: ['queued', 'received', 'started', 'created'].indexOf(state) !== -1, good: state == 'passed', bad: ['errored', 'failed'].indexOf(state) !== -1}">#{{ number }}</strong>
        <a @click="restart_job(job)" v-if="travis_token" :class="{'glyphicon glyphicon-repeat': !restart_state, 'bad glyphicon glyphicon-remove-circle': restart_state === 'ko', 'good glyphicon glyphicon-ok-circle': restart_state === 'ok'}" href="#"></a>
        <a v-if="config.env" :href="job_url" target="_blank">{{ config.env }}</a>
        <a v-if="!config.env" :href="job_url" target="_blank">Job #{{ $index }} </a>
        <i>
            <span v-if="['started'].indexOf(state) !== -1">started <span>{{ started_at | moment("from", true) }}</span></span>
            <span v-if="['queued', 'received', 'started', 'created'].indexOf(state) === -1">
                <i>tooks {{ finished_at | moment("from", started_at, true) }}</i>
            </span>
        </i>
    </div>
</template>

<script>
export default {
  name: 'TravisDetailJob',
  props: ['pull', 'job'],
  data () {
    return this._.merge(this.job, {
      'refreshing': this.pull.pastamaker_travis_detail.refreshing,
      'job_state': this.job.state + '/' + this.job.status,
      'job_url': 'https://api.travis-ci.org/jobs/' + this.job.id + '/log'
    })
  }
}
</script>
