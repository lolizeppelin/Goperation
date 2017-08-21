import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.sql import and_
from sqlalchemy.dialects.mysql import VARCHAR
from sqlalchemy.dialects.mysql import SMALLINT
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.dialects.mysql import BOOLEAN
from sqlalchemy.dialects.mysql import LONGBLOB

from simpleutil.utils import timeutils
from simpleutil.utils import uuidutils

from simpleservice.ormdb.models import MyISAMTableBase
from simpleservice.ormdb.models import InnoDBTableBase
from simpleservice.plugin.models import PluginTableBase

from goperation.plugin import common as plugin_common
from goperation.plugin.manager import common as manager_common


class ResponeDetail(PluginTableBase):
    detail_id = sa.Column(INTEGER(unsigned=True), nullable=False, primary_key=True)
    agent_id = sa.Column(sa.ForeignKey('agentrespones.agent_id', ondelete="CASCADE", onupdate='RESTRICT'),
                         default=0, nullable=False, primary_key=True)
    request_id = sa.Column(sa.ForeignKey('agentrespones.request_id', ondelete="RESTRICT", onupdate='RESTRICT'),
                           nullable=False,
                           primary_key=True)
    resultcode = sa.Column(TINYINT, nullable=False, default=manager_common.RESULT_UNKNOWN)
    result = sa.Column(VARCHAR(manager_common.MAX_DETAIL_RESULT), nullable=False, default='{}')
    __table_args__ = (
            sa.Index('request_id_index', 'request_id'),
            InnoDBTableBase.__table_args__
    )


class AgentRespone(PluginTableBase):
    agent_id = sa.Column(sa.ForeignKey('agents.agent_id', ondelete="CASCADE", onupdate='RESTRICT'),
                         nullable=False,
                         primary_key=True)
    request_id = sa.Column(sa.ForeignKey('asyncrequests.request_id', ondelete="RESTRICT", onupdate='RESTRICT'),
                           nullable=False, primary_key=True)
    server_time = sa.Column(INTEGER(unsigned=True), default=int(timeutils.realnow()), nullable=False)
    # agent respone unix time in seconds
    agent_time = sa.Column(INTEGER(unsigned=True), nullable=False)
    resultcode = sa.Column(TINYINT, nullable=False, default=manager_common.RESULT_UNKNOWN)
    result = sa.Column(VARCHAR(manager_common.MAX_AGENT_RESULT),
                       nullable=False, default='agent respone rpc request')
    details = orm.relationship(ResponeDetail, backref='agentrespone', lazy='select',
                               # primaryjoin="and_(AgentRespone.agent_id==ResponeDetail.agent_id, "
                               #             "AgentRespone.request_id==ResponeDetail.request_id)",
                               primaryjoin=and_(agent_id == ResponeDetail.agent_id,
                                                request_id == ResponeDetail.request_id),
                               cascade='delete,delete-orphan,save-update')
    __table_args__ = (
            sa.Index('request_id_index', 'request_id'),
            InnoDBTableBase.__table_args__
    )


class AsyncRequest(PluginTableBase):
    request_id = sa.Column(VARCHAR(36), default=uuidutils.generate_uuid,
                           nullable=False, primary_key=True)
    request_time = sa.Column(INTEGER(unsigned=True),
                             default=int(timeutils.realnow()), nullable=False)
    # request should finish at finish time
    # when agent get a rpc came, if cur time > finishtime
    # agent will drop the package
    finishtime = sa.Column(INTEGER(unsigned=True), default=int(timeutils.realnow()) + 5, nullable=False)
    # request should finish before deadline time
    # if task scheduler find cur time > deadline, it will not check return any more
    deadline = sa.Column(INTEGER(unsigned=True), default=int(timeutils.realnow())+10, nullable=False)
    # async resopne checker id, means scheduled timer server id
    # 0 means no checker now
    scheduler = sa.Column(INTEGER(unsigned=True), default=0, nullable=False)
    # if request finish
    status = sa.Column(BOOLEAN, nullable=False, default=manager_common.UNFINISH)
    resultcode = sa.Column(TINYINT, nullable=False, default=manager_common.RESULT_UNKNOWN)
    result = sa.Column(VARCHAR(manager_common.MAX_REQUEST_RESULT),
                       nullable=False, default='waiting respone')
    # write agent respone into database
    persist = sa.Column(BOOLEAN, nullable=False, default=1)
    # AgentRespone list
    respones = orm.relationship(AgentRespone, backref='asyncrequest', lazy='select',
                                cascade='delete, delete-orphan')
    __table_args__ = (
        sa.Index('request_time_index', 'request_time'),
        InnoDBTableBase.__table_args__
    )


class AgentResponeBackLog(PluginTableBase):
    """request after deadline scheduled timer will insert a AgentRespone log with status time out
    if agent respone affter deadline, will get an error primary key error
    at this time, recode into  agentresponebacklogs table
    """
    agent_id = sa.Column(INTEGER(unsigned=True), nullable=False, default=0, primary_key=True)
    request_id = sa.Column(VARCHAR(36),
                           nullable=False, primary_key=True)
    server_time = sa.Column(INTEGER(unsigned=True), default=int(timeutils.realnow()), nullable=False)
    agent_time = sa.Column(INTEGER(unsigned=True), nullable=False)
    resultcode = sa.Column(TINYINT, nullable=False, default=manager_common.RESULT_UNKNOWN)
    result = sa.Column(VARCHAR(manager_common.MAX_AGENT_RESULT),
                       nullable=False, default='agent respone rpc request')
    status = sa.Column(BOOLEAN, nullable=False, default=0)
    # will not link to ResponeDetail
    # save respone detail into LONGBLOB column
    details = sa.Column(LONGBLOB, nullable=True)
    __table_args__ = (
            sa.Index('request_id_index', 'request_id'),
            InnoDBTableBase.__table_args__
    )


class AllocatedPort(PluginTableBase):
    agent_id = sa.Column(sa.ForeignKey('agentendpoints.agent_id', ondelete="CASCADE", onupdate='RESTRICT'),
                         nullable=False,
                         primary_key=True)
    port = sa.Column(SMALLINT(unsigned=True), nullable=False,
                     default=0,
                     primary_key=True)
    endpoint = sa.Column(sa.ForeignKey('agentendpoints.endpoint', ondelete="RESTRICT", onupdate='CASCADE'),
                         nullable=False,
                         primary_key=True)
    port_desc = sa.Column(VARCHAR(256), nullable=True, default=None)
    __table_args__ = (
            InnoDBTableBase.__table_args__
    )


class AgentEndpoint(PluginTableBase):
    agent_id = sa.Column(sa.ForeignKey('agents.agent_id', ondelete="CASCADE", onupdate='RESTRICT'),
                         nullable=False,
                         primary_key=True)
    endpoint = sa.Column(VARCHAR(plugin_common.MAX_ENDPOINT_NAME_SIZE),
                         default=None,
                         nullable=False, primary_key=True)
    entiy = sa.Column(INTEGER(unsigned=True), default=0, server_default='0', nullable=False)
    ports = orm.relationship(AllocatedPort, backref='agent', lazy='joined',
                             primaryjoin=and_(agent_id == AllocatedPort.agent_id,
                                              endpoint == AllocatedPort.endpoint),
                             cascade='delete,delete-orphan,save-update')
    __table_args__ = (
            sa.Index('endpoint_index', 'endpoint'),
            InnoDBTableBase.__table_args__
    )


class Agent(PluginTableBase):
    agent_id = sa.Column(INTEGER(unsigned=True), nullable=False,
                         default=1, primary_key=True)
    agent_type = sa.Column(VARCHAR(64), nullable=False)
    create_time = sa.Column(INTEGER(unsigned=True),
                            default=int(timeutils.realnow()), nullable=False)
    host = sa.Column(VARCHAR(plugin_common.MAX_HOST_NAME_SIZE), nullable=False)
    # 0 not active, 1 active  -1 mark delete
    status = sa.Column(TINYINT, default=manager_common.UNACTIVE, nullable=False)
    # total cpu number
    cpu = sa.Column(INTEGER(unsigned=True), server_default='0', nullable=False)
    # total memory can be used
    memory = sa.Column(INTEGER(unsigned=True), server_default='0', nullable=False)
    # total disk space left can be used
    disk = sa.Column(INTEGER(unsigned=True), server_default='0', nullable=False)
    ports_range = sa.Column(VARCHAR(manager_common.MAX_PORTS_RANGE_SIZE),
                            default='',
                            nullable=False)
    endpoints = orm.relationship(AgentEndpoint, backref='agent', lazy='joined',
                                 cascade='delete,delete-orphan,save-update')

    __table_args__ = (
            sa.Index('host_index', 'host'),
            InnoDBTableBase.__table_args__
    )

    @property
    def entiy(self):
        entiy = 0
        for endpoint in self.endpoints:
            entiy += endpoint.entiy
        return entiy

    @property
    def ports(self):
        ports = []
        for endpoint in self.endpoints:
            for port in endpoint.ports:
                ports.append({endpoint.endpoint: port.port})
        return ports


class AgentReportLog(PluginTableBase):
    """Table for recode agent status"""
    # build by Gprimarykey
    report_time = sa.Column(BIGINT(unsigned=True), nullable=False, default=0, primary_key=True)
    agent_id = sa.Column(sa.ForeignKey('agents.agent_id'),
                         nullable=False)
    # psutil.process_iter()
    # status()
    # num_fds()
    # num_threads()  num_threads()
    running = sa.Column(INTEGER(unsigned=True), nullable=False)
    sleeping = sa.Column(INTEGER(unsigned=True), nullable=False)
    num_fds = sa.Column(INTEGER(unsigned=True), nullable=False)
    num_threads = sa.Column(INTEGER(unsigned=True), nullable=False)
    # cpu info  count
    # psutil.cpu_stats() ctx_switches interrupts soft_interrupts
    context = sa.Column(INTEGER(unsigned=True), nullable=False)
    interrupts = sa.Column(INTEGER(unsigned=True), nullable=False)
    sinterrupts = sa.Column(INTEGER(unsigned=True), nullable=False)
    # psutil.cpu_times() irq softirq user system nice iowait
    irq = sa.Column(INTEGER(unsigned=True), nullable=False)
    sirq = sa.Column(INTEGER(unsigned=True), nullable=False)
    # percent of cpu time
    user = sa.Column(TINYINT(unsigned=True), nullable=False)
    system = sa.Column(TINYINT(unsigned=True), nullable=False)
    nice = sa.Column(TINYINT(unsigned=True), nullable=False)
    iowait = sa.Column(TINYINT(unsigned=True), nullable=False)
    # mem info  MB
    # psutil.virtual_memory() used cached  buffers free
    used = sa.Column(INTEGER(unsigned=True), nullable=False)
    cached = sa.Column(INTEGER(unsigned=True), nullable=False)
    buffers = sa.Column(INTEGER(unsigned=True), nullable=False)
    free = sa.Column(INTEGER(unsigned=True), nullable=False)
    # network  count
    # psutil.net_connections()  count(*)
    syn = sa.Column(INTEGER(unsigned=True), nullable=False)
    enable = sa.Column(INTEGER(unsigned=True), nullable=False)
    closeing = sa.Column(INTEGER(unsigned=True), nullable=False)
    __table_args__ = (
            sa.Index('agent_id_index', 'agent_id'),
            MyISAMTableBase.__table_args__
    )
