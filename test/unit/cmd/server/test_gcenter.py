from goperation.cmd.server import http


def main():
    a = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\goperation.conf'
    b = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\gcenter.conf'
    http.run([a, b])


if __name__ == '__main__':
    main()
