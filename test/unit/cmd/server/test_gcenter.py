from goperation.cmd.server import gcenter


def main():
    a = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation.conf'
    b = 'C:\\Users\\loliz_000\\Desktop\\etc\\gcenter.conf'
    c = 'C:\\Users\\loliz_000\\Desktop\\etc\\manager.conf'
    gcenter.run([a, b, c])


if __name__ == '__main__':
    main()
