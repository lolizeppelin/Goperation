import psutil

from simpleutil.utils import jsonutils
from simpleutil.utils import argutils
from simpleutil.log import log as logging

from simpleservice.plugin.httpclient import HttpClientBase
from simpleservice.plugin.exceptions import ServerExecuteRequestError

from goperation.manager import common as manager_common


LOG = logging.getLogger(__name__)


class AgentManagerClient(HttpClientBase):

    USER_AGENT = 'goperation-httpclient'

    agents_path = "/agents"
    agent_path = "/agents/%s"
    agent_ext_path = "/agents/%s/%s"

    endpoints_path = "/agents/%s/endpoints"
    endpoint_path = "/agents/%s/endpoints/%s"
    endpoints_agents_path = "/endpoints/%s/agents"

    entitys_path = "/endpoints/%s/entitys"
    entity_path = "/endpoints/%s/entitys/%s"

    ports_path = "/agents/%s/endpoints/%s/entitys/%s/ports"
    port_path = "/agents/%s/endpoints/%s/entitys/%s/ports/%s"

    asyncs_path = "/asyncrequests"
    async_path = "/asyncrequests/%s"
    async_ext_path = "/asyncrequests/%s/%s"

    files_path = "/files"
    file_path = "/files/%s"
    files_ext_path = "/agents/%s/files"
    file_ext_path = "/agents/%s/files/%s"

    online_path = "/caches/host/%s/online"
    flush_path = "/caches/flush"

    def __init__(self, wsgi_url, wsgi_port, **kwargs):
        super(AgentManagerClient, self).__init__(wsgi_url, wsgi_port, **kwargs)
        self.agent_type = kwargs.pop('agent_type')
        self.local_ip = kwargs.pop('local_ip')
        self.host = kwargs.pop('host')

    # -- agent path --
    def agent_create(self, body):
        resp, results = self.retryable_post(self.agents_path, body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            LOG.error('Agent create self fail: %s' % results['result'])
            raise ServerExecuteRequestError(message='agent create self fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agents_index(self, body):
        resp, results = self.get(action=self.agents_path, body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='list agent fail',
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

    def agent_show(self, agent_id, body=None):
        resp, results = self.get(action=self.agent_path % str(agent_id), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='get agent info fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results['data'][0]

    def agents_update(self, agent_id, body):
        resp, results = self.put(action=self.agent_path % str(agent_id), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='update agent fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agents_status(self, agent_id, body):
        resp, results = self.get(action=self.agent_ext_path % (str(agent_id), 'status'),
                                 body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent check status fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agent_edit(self, agent_id, body):
        resp, results = self.patch(action=self.agent_ext_path % (str(agent_id), 'edit'),
                                   body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='edit agent fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agent_active(self, agent_id, status):
        resp, results = self.patch(action=self.agent_ext_path % (str(agent_id), 'active'),
                                   body={'status': status})
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent active fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agents_upgrade(self, agent_id, body):
        resp, results = self.retryable_post(action=self.agent_ext_path % (str(agent_id), 'upgrade'),
                                            body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent upgrade rpm fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def agent_report(self, agent_id, body):
        resp, results = self.patch(action=self.agent_ext_path % (str(agent_id), 'report'),
                                   body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent report fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    # -- endpoint path --
    def endpoints_index(self, agent_id, body=None):
        resp, results = self.retryable_post(action=self.endpoints_path % str(agent_id),
                                            body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent add endpoint fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def endpoints_add(self, agent_id, endpoints):
        resp, results = self.retryable_post(action=self.endpoints_path % (str(agent_id)),
                                            body={'endpoints': endpoints})
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='add endpoints fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def endpoints_show(self, agent_id, endpoint, body=None):
        if isinstance(endpoint, basestring):
            endpoint = [endpoint, ]
        resp, results = self.get(action=self.endpoint_path % (str(agent_id),
                                                              ','.join(argutils.map_with(endpoint, str))),
                                 body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='delete endpoints fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def endpoints_delete(self, agent_id, endpoint, body=None):
        resp, results = self.delete(action=self.endpoint_path % (str(agent_id),
                                                                 ','.join(argutils.map_with(endpoint, str))),
                                    body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='delete endpoints fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def endpoints_agents(self, endpoint):
        resp, results = self.get(action=self.endpoints_agents_path % endpoint)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='get endpoints agents fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    # -- entity path --
    def entitys_index(self, endpoint, body=None):
        resp, results = self.get(action=self.entitys_path % endpoint, body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='show entitys fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def entitys_add(self, endpoint, body=None):
        resp, results = self.get(action=self.entitys_path % endpoint, body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='add entitys fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def entitys_show(self, endpoint, entitys, body=None):
        resp, results = self.get(action=self.entity_path % (endpoint, ','.join(argutils.map_to_int(entitys))),
                                 body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='add entitys fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def entitys_delete(self, endpoint, entitys, body=None):
        resp, results = self.delete(action=self.entity_path % (endpoint, ','.join(argutils.map_to_int(entitys))),
                                    body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='add entitys fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    # -- port path --
    def ports_index(self, agent_id, endpoint, entity, body=None):
        resp, results = self.get(action=self.ports_path % (str(agent_id), endpoint, str(entity)),
                                 body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='add entitys fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def ports_add(self, agent_id, endpoint, entity, body=None):
        resp, results = self.get(action=self.ports_path % (str(agent_id), endpoint, str(entity)),
                                 body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='add entitys fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def ports_show(self, agent_id, endpoint, entity, ports, body=None):
        resp, results = self.get(action=self.port_path % (str(agent_id), endpoint, str(entity),
                                                          ','.join(argutils.map_with(ports, str))),
                                 body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='add entitys fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def ports_delete(self, agent_id, endpoint, entity, ports, body=None):
        resp, results = self.delete(action=self.port_path % (str(agent_id), endpoint, str(entity),
                                                             ','.join(argutils.map_with(ports, str))),
                                    body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='add entitys fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    # -- asyncrequest path --
    def async_index(self, body):
        resp, results = self.get(action=self.asyncs_path, body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='list asyncrequest info fail',
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
        resp, results = self.get(action=self.async_ext_path % (request_id, 'details'), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='show asyncrequest details fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def async_resopne(self, request_id, body):
        resp, results = self.get(action=self.async_ext_path % (request_id, 'resopne'), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent respone fail',
                                            code=results['resultcode'],
                                            resone=results['result'])

    def scheduler_overtime_respone(self, request_id, body):
        resp, results = self.get(action=self.async_ext_path % (request_id, 'overtime'), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='scheduler overtime report fail',
                                            code=results['resultcode'],
                                            resone=results['result'])

    def scheduler_report(self, request_id, body):
        resp, results = self.get(action=self.async_ext_path % (request_id, 'scheduler'), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='scheduler declare fail',
                                            code=results['resultcode'],
                                            resone=results['result'])

    # -- file path --
    def file_in_agent(self, agent_id, body):
        resp, results = self.retryable_post(action=self.files_ext_path % str(agent_id), body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent list file fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def file_to_agents(self, agent_id, file_id, body):
        resp, results = self.retryable_post(action=self.file_ext_path % (','.join(argutils.map_with(agent_id, str)),
                                                                         file_id),
                                            body=body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent send file fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    # ---- cache path ----
    def cache_flush(self, clean_online_key=False):
        body = dict(online=clean_online_key)

        resp, results = self.post(self.flush_path, body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='cache flush fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    def cache_online(self):
        body = dict(host=self.host,
                    agent_type=self.agent_type,
                    agent_ipaddr=self.local_ip)
        resp, results = self.put(self.online_path % self.host, body)
        if results['resultcode'] != manager_common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent declare online fail',
                                            code=results['resultcode'],
                                            resone=results['result'])
        return results

    # --- ext agent function ---
    def agent_init_self(self,  manager):
        agent_id = self.cache_online()['data'][0]['agent_id']
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
                    endpoints=[endpoint.namespace for endpoint in manager.endpoints],
                    )
        results = self.agent_create(body)
        agent_id = results['data'][0]['agent_id']
        self.agent_id = agent_id
        manager.agent_id = agent_id
