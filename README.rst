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

        方法名  作用域          HTTP方法
index   GET     collection      GET
show    GET     member          GET
create  POST    collection      CREATE
update  PUT     member          PUT
delete  DELETE  member          DELETE
edit    ?       member
new     ?       new

---

RPC调用规范

CAST: 用于不接收执行结果的RPC调用的, 必须预先在rabbit中创建队列

CALL: 用于需要接收执行结果的RPC调用, 必须预先在rabbit中创建队列

NOTIFY: 非RPC信息发送,用于直接发送消息, rabbit中可以不预先创建队列