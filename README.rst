Goperation
==========
游戏运维管理框架

所遵循的RESTful规范

响应状态码

    1xx —— 元数据
    2xx —— 正确的响应
    3xx —— 重定向
    4xx —— 客户端错误
    5xx —— 服务端错误

头部信息

    一般头部：在请求跟响应里都有，跟消息体里传输的数据没有关系。
    请求头部：更多的是关于被请求资源或者客户端的信息。
    响应头部：响应的额外信息。
    实体头部：消息体的额外信息，比如content-length或MIMI-type。

请求方法

    GET:用来从服务器端读取状态
    POST:在服务器端创建某种状态,非幂等
    PUT:主要还是用来在服务器端完整更新资源(Create or Update)
    DELETE:用来在服务器端删除状态
    HEAD:获取元数据
    PATCH:部分修改服务器端数据,局部更新,非幂等

安全性与幂等性

    方法名	安全性	幂等性
    GET	    是	    是
    HEAD	是	    是
    OPTIONS	是	    是
    DELETE	否	    是
    PUT	    否	    是
    POST	否	    否
    PATCH	否	    否

routers对应http方法

    动作    方法    作用域
    index   GET     collection
    show    GET     member
    create  POST    collection
    update  PUT     member
    delete  DELETE  member
    edit    ?       member
    new     ?       new

---

RPC调用规范

    CAST: 用于不接收执行结果的RPC调用的,必须预先在rabbit中创建队列,target中有fanout标记使用广播交换机广播发送

    CALL: 用于需要接收执行结果的RPC调用, 必须预先在rabbit中创建队列

    NOTIFY: 非RPC信息发送,用于直接发送消息, rabbit中可以不预先创建队列


---

Manager work_lock调用
优先级  方法                         说明
0       rpc_delete_agent_precommit   锁定后检查状态必须大于SOFTBUSY
                                     调用endpoint.empty(),确保endpoint.empty()无阻塞无IO且能
0       rpc_delete_agent_postcommit  无IO,无阻塞  锁定后检查状态必须等于PERDELETE
                                     会调用suicide, suicide中有schedule_call_global调用,执行时间短

0       agent_id                     无IO,无阻塞, 初始设置agent_id
1       post_start                   无IO,无阻塞  初始设置状态 调用force_status
3       frozen_port                  无IO,无阻塞  申请端口
2       free_ports                   无IO,无阻塞  释放端口

5       is_active                    无IO,无阻塞, 返回是否在ACTIVE状态
0       force_status                 无IO,无阻塞  无视当前状态的情况下修改状态
1       set_status                   无IO,无阻塞  修改状态,当前状态必须大于等于SOFTBUSY

1       rpc_active_agent             无IO,无阻塞  服务端rpc设置状态,  调用set_status
1       rpc_upgrade_agent            无IO,无阻塞  转换为HARDBUSY状态, 调用set_status


Manager 状态说明
ACTIVE = 1                           激活状态,endpoint的rpc调用必须大于等于这个状态中才能执行
UNACTIVE = 0                         为激活状态,刚注册的服务默认这个状态
SOFTBUSY = -10                       软忙状态, 小于这个状态会直接要求rpc重发（PERDELETE除外）
                                     等于这个状态会延迟0.5秒重新检查,如果还是小于等于这个状态,通知rpc重发
INITIALIZING = -20                   Agent启动完毕之前属于这个状态
HARDBUSY = -30                       硬忙状态,目前用于Agent端rpm升级
DELETED = -127                       已经删除状态,在收到系统信号退出前,Agent是这个状态
PERDELETE = -128                     等待删除状态,特殊状态,唯一小于软忙状态不需要rpc重发的状态