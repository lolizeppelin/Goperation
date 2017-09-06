from goperation.cmd.agent import scheduler


def main():
    a = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation.conf'
    b = 'C:\\Users\\loliz_000\\Desktop\\etc\\agent.conf'
    try:
        scheduler.run([a, b])
    except Exception as e:
        print e

if __name__ == '__main__':
    main()
