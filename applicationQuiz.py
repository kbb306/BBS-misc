import QuizSource
import os
def printer(text,num=None,uid=None):
    if uid is not None:
        text = text.replace("@",f"[{uid}]")
    if num is not None:
            text.replace("#",num)
    text.replace("^","\n")
    print(text)

def parser(number):
    DICTIONARY = QuizSource.QUESTIONS
    os.system('cls' if os.name == 'nt' else 'clear')
    question = DICTIONARY[number]
    printer(QuizSource.HEADER)
    if question[type] == "T":
        printer("".join(question["question"],"^^"))
        answer = input("> ")
    else:
        printer("".join(question["question"],"^^"))
        
        for i in len(question["choices"]):
            if i < 10:
                printer("".join("0{i}]",question["choices"][i]))
            else:
                printer("".join("{i}]",question["choices"][i]))
            printer("^^")
            answer = input("> ")
            if answer not in range(len(question["choices"])):
                parser(number)
    if answer == ("help" or "HELP"):
        printer(QuizSource.HELP_RAW)
def main():
    printer(QuizSource.INTRO_RAW)
    while input() != "CONTINUE":
        os.system('cls' if os.name == 'nt' else 'clear')
        printer(QuizSource.INTRO_RAW)
    printer(QuizSource.UIN_NOTICE_RAW)
    while input() != "CONTINUE":
        os.system('cls' if os.name == 'nt' else 'clear')
        printer(QuizSource.UIN_NOTICE_RAW)
    for each in QuizSource.QUESTIONS:
        parser(QuizSource.QUESTIONS[each]["id"])
    printer(QuizSource.FINISH_RAW)
    input()
    printer(QuizSource.FAIL_RAW)
main()