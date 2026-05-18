-- Скрипт создания базы данных ООО "МебельОрг"
-- Создано автоматически на основе db.py

PRAGMA foreign_keys = ON;

-- Таблица ролей
CREATE TABLE IF NOT EXISTS Roles (
    RoleId INTEGER PRIMARY KEY,
    RoleName TEXT NOT NULL UNIQUE
);

-- Таблица пользователей
CREATE TABLE IF NOT EXISTS Users (
    UserId INTEGER PRIMARY KEY AUTOINCREMENT,
    FullName TEXT NOT NULL,
    Login TEXT NOT NULL UNIQUE,
    Password TEXT NOT NULL,
    RoleId INTEGER NOT NULL,
    FOREIGN KEY(RoleId) REFERENCES Roles(RoleId)
);

-- Таблица поставщиков
CREATE TABLE IF NOT EXISTS Suppliers (
    SupplierId INTEGER PRIMARY KEY AUTOINCREMENT,
    SupplierName TEXT NOT NULL UNIQUE
);

-- Таблица производителей
CREATE TABLE IF NOT EXISTS Manufacturers (
    ManufacturerId INTEGER PRIMARY KEY AUTOINCREMENT,
    ManufacturerName TEXT NOT NULL UNIQUE
);

-- Таблица категорий товаров
CREATE TABLE IF NOT EXISTS Categories (
    CategoryId INTEGER PRIMARY KEY AUTOINCREMENT,
    CategoryName TEXT NOT NULL UNIQUE
);

-- Таблица единиц измерения
CREATE TABLE IF NOT EXISTS Units (
    UnitId INTEGER PRIMARY KEY AUTOINCREMENT,
    UnitName TEXT NOT NULL UNIQUE
);

-- Таблица товаров
CREATE TABLE IF NOT EXISTS Products (
    ProductId INTEGER PRIMARY KEY AUTOINCREMENT,
    Article TEXT NOT NULL UNIQUE,
    ProductName TEXT NOT NULL,
    Description TEXT,
    CategoryId INTEGER NOT NULL,
    ManufacturerId INTEGER NOT NULL,
    SupplierId INTEGER NOT NULL,
    UnitId INTEGER NOT NULL,
    Price REAL NOT NULL CHECK(Price >= 0),
    DiscountPercent REAL NOT NULL CHECK(DiscountPercent >= 0),
    StockQty INTEGER NOT NULL CHECK(StockQty >= 0),
    PhotoPath TEXT,
    FOREIGN KEY(CategoryId) REFERENCES Categories(CategoryId),
    FOREIGN KEY(ManufacturerId) REFERENCES Manufacturers(ManufacturerId),
    FOREIGN KEY(SupplierId) REFERENCES Suppliers(SupplierId),
    FOREIGN KEY(UnitId) REFERENCES Units(UnitId)
);

-- Таблица пунктов выдачи
CREATE TABLE IF NOT EXISTS PickupPoints (
    PickupPointId INTEGER PRIMARY KEY AUTOINCREMENT,
    Address TEXT NOT NULL UNIQUE
);

-- Таблица статусов заказов
CREATE TABLE IF NOT EXISTS OrderStatuses (
    StatusId INTEGER PRIMARY KEY AUTOINCREMENT,
    StatusName TEXT NOT NULL UNIQUE
);

-- Таблица заказов
CREATE TABLE IF NOT EXISTS Orders (
    OrderId INTEGER PRIMARY KEY AUTOINCREMENT,
    OrderNumber INTEGER NOT NULL UNIQUE,
    OrderDate TEXT NOT NULL,
    DeliveryDate TEXT NOT NULL,
    PickupPointId INTEGER NOT NULL,
    CustomerUserId INTEGER,
    ReceiveCode INTEGER NOT NULL,
    StatusId INTEGER NOT NULL,
    FOREIGN KEY(PickupPointId) REFERENCES PickupPoints(PickupPointId),
    FOREIGN KEY(CustomerUserId) REFERENCES Users(UserId),
    FOREIGN KEY(StatusId) REFERENCES OrderStatuses(StatusId)
);

-- Таблица позиций заказа
CREATE TABLE IF NOT EXISTS OrderItems (
    OrderItemId INTEGER PRIMARY KEY AUTOINCREMENT,
    OrderId INTEGER NOT NULL,
    ProductId INTEGER NOT NULL,
    Quantity INTEGER NOT NULL CHECK(Quantity > 0),
    FOREIGN KEY(OrderId) REFERENCES Orders(OrderId) ON DELETE CASCADE,
    FOREIGN KEY(ProductId) REFERENCES Products(ProductId),
    UNIQUE(OrderId, ProductId)
);

-- Начальные данные: роли
INSERT OR IGNORE INTO Roles(RoleId, RoleName) VALUES (1, 'Администратор');
INSERT OR IGNORE INTO Roles(RoleId, RoleName) VALUES (2, 'Менеджер');
INSERT OR IGNORE INTO Roles(RoleId, RoleName) VALUES (3, 'Авторизированный клиент');

-- Начальные данные: статусы заказов
INSERT OR IGNORE INTO OrderStatuses(StatusName) VALUES ('Новый');
INSERT OR IGNORE INTO OrderStatuses(StatusName) VALUES ('Завершен');
INSERT OR IGNORE INTO OrderStatuses(StatusName) VALUES ('В обработке');
INSERT OR IGNORE INTO OrderStatuses(StatusName) VALUES ('Отменен');
