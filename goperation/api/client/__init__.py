from simpleutil.utils import argutils
from simpleutil.log import log as logging

from simpleservice import common

from simpleservice.plugin.httpclient import HttpClientBase
from simpleservice.plugin.exceptions import ServerExecuteRequestError


LOG = logging.getLogger(__name__)


class ManagerClient(HttpClientBase):

    USER_AGENT = 'goperation-httpclient'

    agents_path = "/agents"
    agent_path = "/agents/%s"
    agent_ext_path = "/agents/%s/%s"

    endpoints_path = "/agents/%s/endpoints"
    endpoint_path = "/agents/%s/endpoints/%s"
    endpoints_ex_path = "/endpoints/%s/%s"

    entitys_agent_path = "/agents/%s/endpoints/%s/entitys"
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

    # -- agent path --
    def agent_create(self, body):
        resp, results = self.retryable_post(self.agents_path, body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            LOG.error('Agent create self fail: %s' % results['result'])
            raise ServerExecuteRequestError(message='agent create self fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def agents_index(self, body=None):
        resp, results = self.get(action=self.agents_path, body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='list agent fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def agent_delete(self, agent_id, body):
        resp, results = self.delete(action=self.agent_path % str(agent_id), body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='delete agent fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def agent_show(self, agent_id, body=None):
        resp, results = self.get(action=self.agent_path % str(agent_id), body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='get agent info fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def agents_update(self, agent_id, body):
        resp, results = self.put(action=self.agent_path % str(agent_id), body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='update agent fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def agents_status(self, agent_id, body):
        resp, results = self.get(action=self.agent_ext_path % (str(agent_id), 'status'),
                                 body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent check status fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def agent_edit(self, agent_id, body):
        resp, results = self.patch(action=self.agent_ext_path % (str(agent_id), 'edit'),
                                   body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='edit agent fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def agent_active(self, agent_id, status):
        resp, results = self.patch(action=self.agent_ext_path % (str(agent_id), 'active'),
                                   body={'status': status})
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent active fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def agents_upgrade(self, agent_id, body):
        resp, results = self.retryable_post(action=self.agent_ext_path % (str(agent_id), 'upgrade'),
                                            body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent upgrade rpm fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def agent_report(self, agent_id, body):
        resp, results = self.patch(action=self.agent_ext_path % (str(agent_id), 'report'),
                                   body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent report fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def agent_clean(self, agent_id):
        resp, results = self.post(action=self.agent_ext_path % (str(agent_id), 'clean'))
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='clean deleted agent fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    # -- endpoint path --
    def endpoints_index(self, agent_id, body=None):
        resp, results = self.get(action=self.endpoints_path % str(agent_id),
                                 body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent add endpoint fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def endpoints_add(self, agent_id, endpoints):
        resp, results = self.retryable_post(action=self.endpoints_path % (str(agent_id)),
                                            body={'endpoints': endpoints})
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='add endpoints fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def endpoints_show(self, agent_id, endpoint, body=None):
        resp, results = self.get(action=self.endpoint_path % (str(agent_id), endpoint),
                                 body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='delete endpoints fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def endpoints_delete(self, agent_id, endpoint, body=None):
        resp, results = self.delete(action=self.endpoint_path % (str(agent_id),
                                                                 ','.join(argutils.map_with(endpoint, str))),
                                    body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='delete endpoints fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def endpoint_agents(self, endpoint):
        resp, results = self.get(action=self.endpoints_ex_path % (endpoint, 'agents'))
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='get endpoints agents fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def endpoint_entitys(self, endpoint):
        resp, results = self.get(action=self.endpoints_ex_path % (endpoint, 'entitys'))
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='get endpoints entitys fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    # -- entity path --
    entitys_index = endpoint_entitys

    def entitys_agent_index(self, agent_id, endpoint, body=None):
        resp, results = self.get(action=self.entitys_agent_path % (str(agent_id), endpoint),
                                 body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='show entitys fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def entitys_add(self, agent_id, endpoint, body):
        resp, results = self.retryable_post(action=self.entitys_agent_path % (str(agent_id), endpoint),
                                            body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='add entitys fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def entitys_show(self, endpoint, entitys, body=None):
        resp, results = self.get(action=self.entity_path % (endpoint,
                                                            ','.join(argutils.map_with(entitys, str))),
                                 body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='add entitys fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def entitys_delete(self, endpoint, entitys, body=None):
        resp, results = self.delete(action=self.entity_path % (endpoint,
                                                               ','.join(argutils.map_with(entitys, str))),
                                    body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='add entitys fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    # -- port path --
    def ports_index(self, agent_id, endpoint, entity, body=None):
        resp, results = self.get(action=self.ports_path % (str(agent_id), endpoint, str(entity)),
                                 body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='add entitys fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def ports_add(self, agent_id, endpoint, entity, body=None):
        resp, results = self.retryable_post(action=self.ports_path % (str(agent_id), endpoint, str(entity)),
                                            body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='add entitys fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def ports_delete(self, agent_id, endpoint, entity, ports, body=None):
        resp, results = self.delete(action=self.port_path % (str(agent_id), endpoint, str(entity),
                                                             ','.join(argutils.map_with(ports, str))),
                                    body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='add entitys fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    # -- asyncrequest path --
    def asyncs_index(self, body):
        resp, results = self.get(action=self.asyncs_path, body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='list asyncrequest info fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def async_show(self, request_id, body):
        resp, results = self.get(action=self.async_path % request_id, body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='show asyncrequest info fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def async_details(self, request_id, body):
        """get asyncrequest result of target agent"""
        resp, results = self.get(action=self.async_ext_path % (request_id, 'details'), body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='show asyncrequest details fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def async_response(self, request_id, body):
        """agent respone asyncrequest result"""
        resp, results = self.retryable_post(action=self.async_ext_path % (request_id, 'response'), body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent respone fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def async_responses(self, request_id, body):
        """get respone agents list"""
        resp, results = self.get(action=self.async_ext_path % (request_id, 'responses'), body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='get respone agents list fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def async_overtime(self, request_id, body):
        """scheduler respone asyncrequest over deadline"""
        resp, results = self.put(action=self.async_ext_path % (request_id, 'overtime'), body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='scheduler overtime fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    # -- file path --
    def files_index(self):
        resp, results = self.get(action=self.files_path)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='list file fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def file_add(self, body):
        resp, results = self.retryable_post(action=self.files_path, body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='add file fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def file_show(self, file_id):
        resp, results = self.get(action=self.file_path % file_id)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='show file fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def file_delete(self, file_id, body):
        resp, results = self.delete(action=self.file_path % file_id, body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='delete file fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def file_in_agent(self, agent_id, body):
        resp, results = self.post(action=self.files_ext_path % str(agent_id), body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent list file fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def add_file_to_agents(self, agent_id, file_id, body):
        resp, results = self.put(action=self.file_ext_path % (','.join(argutils.map_with(agent_id, str)), file_id),
                                 body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent send file fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def delete_file_from_agents(self, agent_id, file_id, body):
        resp, results = self.delete(action=self.file_ext_path % (str(agent_id), file_id), body=body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent delete file fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    # ---- cache path ----
    def cache_flush(self, clean_online_key=False):
        body = dict(online=clean_online_key)

        resp, results = self.post(self.flush_path, body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='cache flush fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results

    def cache_online(self, host, local_ip, agent_type):
        body = dict(host=host,
                    agent_type=agent_type,
                    agent_ipaddr=local_ip)
        resp, results = self.retryable_post(self.online_path % host, body)
        if results['resultcode'] != common.RESULT_SUCCESS:
            raise ServerExecuteRequestError(message='agent declare online fail:%d' % results['resultcode'],
                                            code=resp.status_code,
                                            resone=results['result'])
        return results


class GopHttpClientApi(object):

    def __init__(self, httpclient):
        if not isinstance(httpclient, ManagerClient):
            raise TypeError('httpclient must class of ManagerClient')
        self.httpclient = httpclient

    def __getattr__(self, attrib):
        if not hasattr(self.httpclient, attrib):
            raise AttributeError('%s has no attrib %s' % (self.__class__.__name__, attrib))
        return getattr(self.httpclient, attrib)
