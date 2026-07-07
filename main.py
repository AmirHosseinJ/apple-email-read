import outlook


def print_hi(name):
    mail = outlook.Outlook()
    mail.login('emailaccount@live.com', 'yourpassword')
    mail.inbox()
    print (mail.unread())


if __name__ == '__main__':
    print_hi('PyCharm')

