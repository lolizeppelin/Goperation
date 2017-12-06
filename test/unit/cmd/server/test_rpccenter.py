from goperation.cmd.server import rpc


def main():
    a = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\goperation.conf'
    b = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\agent.conf'
    c = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\endpoints'
    rpc.run('gcenter-rpc', [a, b], c)


if __name__ == '__main__':
    main()
