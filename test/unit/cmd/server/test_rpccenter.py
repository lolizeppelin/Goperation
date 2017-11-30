from goperation.cmd.server import rpc


def main():
    a = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\goperation.conf'
    b = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\agent.conf'
    rpc.run([a, b])


if __name__ == '__main__':
    main()
