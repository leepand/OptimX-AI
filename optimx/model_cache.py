# 新的类用于管理模型在数据库中的存储和加载
class ModelManager:
    def __init__(self, model_db):
        self.model_db = model_db

    def get_model(self, model_id, key, model_init_func=None, save_init_model=False):
        """
        从缓存数据库中获取指定模型ID和键对应的模型。

        :param model_id: 模型的唯一标识符
        :param key: 模型参数在数据库中的键
        :param model_init_func: 可选参数，模型初始化函数，用于在获取不到模型时返回默认结果。
        :return: 对应的模型数据，如果不存在且未传入初始化函数则返回None，否则返回初始化函数的结果。
        """
        try:
            model = self.model_db.get((model_id, key))
            if model is None and model_init_func is not None:
                model = model_init_func()
                if save_init_model:
                    self.save_model(model_id, key, model)
            return model
        except Exception as e:
            print(f"Error occurred while getting model: {e}")
            return None

    def save_model(self, model_id, key, value):
        """
        将模型数据保存到缓存数据库中。

        :param model_id: 模型的唯一标识符
        :param key: 模型参数在数据库中的键
        :param value: 要保存的模型数据
        """
        try:
            self.model_db[(model_id, key)] = value
        except Exception as e:
            print(f"Error occurred while saving model: {e}")

    def delete_model(self, model_id, key):
        """
        从缓存数据库中删除指定模型ID和键对应的模型数据。

        :param model_id: 模型的唯一标识符
        :param key: 模型参数在数据库中的键
        """
        try:
            if (model_id, key) in self.model_db:
                del self.model_db[(model_id, key)]
        except Exception as e:
            print(f"Error occurred while deleting model: {e}")

    def model_exists(self, model_id, key):
        """
        检查指定模型ID和键的模型是否存在于缓存数据库中。

        :param model_id: 模型的唯一标识符
        :param key: 模型参数在数据库中的键
        :return: 如果模型存在则返回True，否则返回False
        """
        return (model_id, key) in self.model_db
