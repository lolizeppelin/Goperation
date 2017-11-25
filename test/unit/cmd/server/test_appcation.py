from goperation.cmd.agent import application


def main():
    a = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\goperation.conf'
    b = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\agent.conf'
    c = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\endpoints'
    application.run([a, b], config_dirs=c)


if __name__ == '__main__':
    main()
