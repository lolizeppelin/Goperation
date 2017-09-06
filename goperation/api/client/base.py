import psutil

from simpleutil.utils import jsonutils
from simpleutil.log import log as logging

from simpleservice.plugin.httpclient import HttpClientBase
from simpleservice.plugin.exceptions import ServerExecuteRequestError

from goperation.plugin.manager import common as manager_common


LOG = logging.getLogger(__name__)


class ManagerClient(HttpClientBase):

    USER_AGENT = 'goperation-httpclient'

    agent_path = "/agents/%s"
    agent_active_path = "/agents/%s/active"
    agent_edit_path = "/agents/%s/edit"
    agent_posts_path = "/agents/%s/ports"
    agent_endpoints_path = "/agents/%s/endpoints"
    agent_online_path = "/agents/online"

    agents_path = "/agents"
    agents_flush_path = "/agents/flush"
    agents_file_path = "/agents/%s/file"
    agents_upgrade_path = "/agents/%s/upgrade"
    agents_status_path = "/agents/%s/status"

    asyncs_path = "/asyncrequests"
    async_path = "/asyncrequests/%s"
    async_scheduler_report_path = "/asyncrequests/%s/scheduler"
    async_scheduler_report_overtime_path = "/asyncrequests/%s/overtime"
    async_respone_path = "/asyncrequests/%s/respone"
    async_respone_details_path = "/asyncrequests/%s/details"

    def agent_create(self, body):
        resp, results = self.retryable_post(self.agents_path, body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            LOG.error('Agent create self fail: %s' % results['result'])
            raise ServerExecuteRequestError(message='agent create self fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agent_delete(self, agent_id, body):
        resp, results = self.delete(action=self.agent_path % str(agent_id), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='delete agent fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agent_show(self, agent_id):
        resp, results = self.get(action=self.agent_path % str(agent_id))
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='get agent info fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results['data'][0]

    def agent_edit(self, agent_id, body):
        resp, results = self.patch(action=self.agent_edit_path % str(agent_id), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='edit agent fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agent_active(self, agent_id, status):
        resp, results = self.patch(action=self.agent_active_path % str(agent_id),
                                   body={'status': status})
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent active fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agent_get_ports(self, agent_id, body):
        resp, results = self.get(action=self.agents_file_path % str(agent_id), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent get posts fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agent_add_ports(self, agent_id, body):
        resp, results = self.retryable_post(action=self.agent_posts_path % str(agent_id), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent add posts fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agent_delete_ports(self, agent_id, body):
        resp, results = self.delete(action=self.agent_posts_path % str(agent_id), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent delete posts fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agent_add_endpoints(self, agent_id, body):
        resp, results = self.retryable_post(action=self.agent_endpoints_path % str(agent_id), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent add posts fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agents_delete_endpoints(self, agent_id, body):
        resp, results = self.delete(action=self.agent_endpoints_path % str(agent_id), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent delete posts fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    # bulk agent request

    def agents_index(self, body):
        resp, results = self.get(action=self.agents_path, body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='list agent fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agents_update(self, agent_id, body):
        resp, results = self.put(action=self.agent_path % str(agent_id), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='update agent fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agents_status(self, agent_id, body):
        resp, results = self.get(action=self.agents_status_path % str(agent_id), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent check status fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agents_upgrade(self, agent_id, body):
        resp, results = self.retryable_post(action=self.agents_upgrade_path % str(agent_id), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent upgrade rpm fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agents_file(self, agent_id, body):
        resp, results = self.retryable_post(action=self.agents_file_path % str(agent_id), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent send file fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    # async request

    def async_index(self, body):
        resp, results = self.get(action=self.asyncs_path, body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='get asyncrequest list fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def async_show(self, request_id, body):
        resp, results = self.get(action=self.async_path % request_id, body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='show asyncrequest info fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def async_details(self, request_id, body):
        resp, results = self.get(action=self.async_respone_details_path % request_id, body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='show asyncrequest details fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def async_resopne(self, request_id, body):
        resp, results = self.retryable_post(self.async_respone_path % request_id, body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent respone fail',
                                            code=results['resultcode'],
                                            resone=results['result'])

    def agent_report_online(self, performance_snapshot=None):
        body = dict(host=self.host,
                    agent_type=self.agent_type,
                    agent_ipaddr=self.local_ip)
        if performance_snapshot:
            body.setdefault('extdata', {'snapshot': performance_snapshot})
        resp, results = self.put(self.agent_online_path, body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent report online fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        agent_id = results['data'][0]['agent_id']
        if agent_id != self.agent_id:
            raise RuntimeError('Agent id changed %d in here, '
                               'but get %d from gcenter' % (self.agent_id, agent_id))

    def agent_flush(self, clean_online_key=False):
        body = dict(online=clean_online_key)

        resp, results = self.post(self.agents_flush_path, body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent flush fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def scheduler_overtime_respone(self, request_id, body):
        resp, results = self.put(self.async_scheduler_report_overtime_path % request_id, body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='scheduler overtime report fail',
                                            code=results['resultcode'],
                                            resone=results['result'])

    def scheduler_report(self, request_id, body):
        resp, results = self.retryable_post(self.async_scheduler_report_path % request_id, body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='scheduler declare fail',
                                            code=results['resultcode'],
                                            resone=results['result'])

    # Ext function

    def agent_init_self(self,  manager):
        body = dict(host=self.host,
                    agent_type=self.agent_type,
                    agent_ipaddr=self.local_ip)
        resp, results = self.put(self.agent_online_path, body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent declare online fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        agent_id = results['data'][0]['agent_id']
        if agent_id is None:
            self.agent_create_self(manager)
        else:
            if self.agent_id is not None:
                if self.agent_id != agent_id:
                    raise RuntimeError('Agent init find agent_id changed!')
                LOG.warning('Do not call agent_init_self more then once')
            self.agent_id = agent_id
            manager.agent_id = agent_id

    def agent_create_self(self, manager):
        """agent notify gcenter add agent"""
        body = dict(host=self.host,
                    agent_type=self.agent_type,
                    cpu=psutil.cpu_count(),
                    # memory available MB
                    memory=psutil.virtual_memory().available/(1024*1024),
                    disk=manager.partion_left_size,
                    ports_range=jsonutils.dumps_as_bytes(manager.ports_range),
                    endpoints=[endpoint.__class__.__name__.lower() for endpoint in manager.endpoints],
                    )
        results = self.agent_create(body)
        agent_id = results['data'][0]['agent_id']
        self.agent_id = agent_id
        manager.agent_id = agent_id
