from goperation.cmd.agent import application


def main():
    a = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation.conf'
    b = 'C:\\Users\\loliz_000\\Desktop\\etc\\agent.conf'
    application.run([a, b])


if __name__ == '__main__':
    main()
