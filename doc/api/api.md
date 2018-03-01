以下str类型在未注明情况下不可输入中文


--------------------列出可用域
PATH      /gopcdn/cdndomains
method    GET

必要参数
无

可选参数
page_num	    页码,默认0


----返回
data列表结构

entity          域实体id                     int
internal        是否内部域                   boolean
agent_id        域实体所在服务器id           int
port            域监听端口                   int
character_set   域编码                       str
domains         域名列表                     list（str）

备注
这个接口用于后面[创建资源]时选择传入的域名的entity
[创建资源]可以选域实体需要跳过internal为True的记录



--------------------查询指定域
PATH      /gopcdn/cdndomains/{entity}
method    GET

必要参数
无

可选参数
resources	    是否列出域所包含资源信息			boolean


----返回
data列表结构

entity          域实体id                     int
internal        是否内部域                   boolean
port            域监听端口                   int
character_set   域编码                       str
domains         域名列表                     list（str）
agent_id        域实体所在服务器id           int
metadata        服务器元数据                 object
resources       资源列表信息                 object


备注
这个接口用于通过域entity查询域详细信息的情况




--------------------创建资源
PATH      /gopcdn/cdnresources
method    POST

必要参数
name			资源名,输入框填写                    str
etype			资源类型,输入框填写				    str
entity          域实体,从[列出可用域]接口            int
                返回值中选取entity值传入

可选参数
impl            资源更新方式,可选值为[svn,websocket]  str
auth            资源更新认证方式                      object
desc            资源说明,可使用中文                   str


----返回
data列表结构

resource_id          资源id              int
etype                资源类型            str
name                 资源名              str
impl                 资源更新方式        str


备注
无




--------------------列出资源
PATH      /gopcdn/cdnresources
method    GET

必要参数
name			资源名,输入框填写                    str
etype			资源类型,输入框填写				    str
entity          域实体,从[列出可用域]接口的          int
                返回值选取传入entity


可选参数
impl            资源更新方式,可选值为[svn,websocket]  str
auth            资源更新认证方式                      object
desc            资源说明,可使用中文                   str


----返回
data列表结构
resource_id          资源id              int
entity               域实体id            int
etype                资源类型            str
name                 资源名              str
impl                 资源更新方式        str
status               资源状态            int
quotes               直接引用次数        int


备注
这个接口提供后面[创建包记录]时选择传入的资源resource_id
[创建包记录]可以资源需要跳过status为0的记录





--------------------列出资源版本列表
PATH      /gopcdn/cdnresources/{resource_id}/version
method    GET

必要参数
无


可选参数
无


----返回
data列表结构
resource_id          资源id               int
version_id           版本号id(主键)       int
version              版本号               str
vtime                版本号更新时间       int
desc                 版本号说明,可中文    str



备注
这个提供用于后面[修改包记录]时,列出可选的默认资源版本号列表






--------------------------------------------------------------------------------





--------------------创建包记录
PATH      /gogamechen1/group/{group_id}/packages
method    POST

必要参数
resource_id    包引用游戏资源id,从[列出资源]接口选取          int
package_name   包名,页面填写,开发规定                        str
mark	       包标记,页面填写                               str

可选参数
extension      扩展标记, json结构                            object
magic          特殊标记, json结构                            object
desc           说明字段, 允许中文                            str


----返回
data列表结构
resource_id                资源id              int
package_name               包名                str
mark                       包标记              str
magic                      特殊标记            objcet
extension                  扩展标记            objcet
group_id                   包所在游戏组        int
desc                       包说明


备注
这个接口提供[上传包文件]时所需的package_id



--------------------修改包记录
PATH      /gogamechen1/group/{group_id}/packages/{package_id}
method    PUT

必要参数
无

可选参数
extension      扩展标记, json结构                                 object
magic          特殊标记, json结构                                 object
status         包状态, 可选参数[0, 1]                             int
gversion       包版本号,从[列出包文件]接口列表中选取传入gversion   str
rversion       资源版本号,从[列出资源版本列表]列表选取传入version  str
desc           说明字段, 允许中文                                 str


----返回
data列表结构
无


备注
无




--------------------上传包文件
PATH      /gogamechen1/package/{package_id}/pfiles
method    POST

必要参数
gversion      包版本号                                  str
ftype         包类型,可选值[full,small]                 str


可选参数
address       安装包地址                               str

如果address值为空,fileinfo为必选参数
fileinfo      包信息,结构为                            object
              ['md5', 'crc32', 'size', 'filename']
可选参数
timeout       上传超时时间                             int
desc          包文件说明                               str


desc           说明字段, 允许中文                            str


----返回
data列表结构
pfile_id                包文件id                       int
uri                     websocket上传地址              str
                        使用外部地址返回null

备注
address为空会返回websocket上传地址,前端调用websocket上传文件




--------------------列出包文件
PATH      /gogamechen1/package/{package_id}/pfiles
method    GET


必要参数
无

可选参数
page_num



----返回
data列表结构
pfile_id                包文件id              int
ftype                   包类型                str
gversion                包版本号              str
address                 包url地址             str
status                  包状态                int
utime                   包上传时间            int



备注
这个接口提供[修改包记录]时,所需的可选的包版本号列表



--------------------删除包文件
PATH      /gogamechen1/package/{package_id}/pfiles/{pfile_id}
method    GET


必要参数
无

可选参数
无



----返回
data列表结构
pfile_id                包文件id              int