from goperation.cmd.server import wsgi


def main():
    a = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\goperation.conf'
    b = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\gcenter.conf'
    c = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\endpoints'
    wsgi.run('gcenter-wsgi', [a, b], c)


if __name__ == '__main__':
    main()
