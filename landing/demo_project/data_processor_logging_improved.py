import logging

logger = logging.getLogger(__name__)

# 初期状態：ボロボロのコード
def process_data(data):
    result = []
    for i in range(len(data)):
        for j in range(len(data)):
            if i != j:
                if data[i] == data[j]:
                    result.append(data[i])
    return list(set(result))

def calculate_stats(numbers):
    total = 0
    for n in numbers:
        total = total + n
    avg = total / len(numbers)
    return {"sum": total, "average": avg}

def load_file(filename):
    f = open(filename, 'r')
    content = f.read()
    f.close()
    return content

def save_results(data, filename):
    f = open(filename, 'w')
    f.write(str(data))
    f.close()

class DataManager:
    def __init__(self):
        self.items = []
    
    def add(self, item):
        self.items.append(item)
    
    def get_all(self):
        return self.items
    
    def find_duplicates(self):
        dups = []
        for i in self.items:
            count = 0
            for j in self.items:
                if i == j:
                    count += 1
            if count > 1 and i not in dups:
                dups.append(i)
        return dups
