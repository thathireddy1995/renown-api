"""Report / dashboard response DTOs."""

from pydantic import BaseModel


class DayPoint(BaseModel):
    day: str
    revenue: float = 0
    orders: int = 0


class CategorySlice(BaseModel):
    name: str
    value: float


class NamedKpi(BaseModel):
    label: str
    value: str


class AdminReportsResponse(BaseModel):
    revenueTrend: list[DayPoint]
    categoryMix: list[CategorySlice]
    kpis: list[NamedKpi]


class DashboardKpi(BaseModel):
    label: str
    value: str
    delta: str


class RecentOrderRow(BaseModel):
    id: str
    customer: str
    status: str
    total: float


class TopProductProp(BaseModel):
    id: str
    name: str
    brand: str
    image: str
    price: float


class LowStockProp(BaseModel):
    sku: str
    name: str
    warehouse: str
    stock: int


class AdminDashboardResponse(BaseModel):
    periodLabel: str
    kpis: list[DashboardKpi]
    salesByDay: list[DayPoint]
    recentOrders: list[RecentOrderRow]
    topProducts: list[TopProductProp]
    lowStockAlerts: list[LowStockProp]


class MonthPoint(BaseModel):
    m: str
    v: float


class StaffSalesPoint(BaseModel):
    name: str
    sales: float


class StaffStoreReportsResponse(BaseModel):
    kpis: list[DashboardKpi]
    revenueTrend: list[MonthPoint]
    topStaff: list[StaffSalesPoint]


class WeekPoint(BaseModel):
    d: str
    v: float


class CategoryUnits(BaseModel):
    name: str
    v: float


class StoreRecentOrder(BaseModel):
    id: str
    customer: str
    items: str
    total: str
    status: str


class StoreAppointment(BaseModel):
    time: str
    name: str
    type: str
    doctor: str


class StaffStoreDashboardResponse(BaseModel):
    kpis: list[DashboardKpi]
    weeklySales: list[WeekPoint]
    salesByCategory: list[CategoryUnits]
    recentOrders: list[StoreRecentOrder]
    appointments: list[StoreAppointment]
    weeklyDelta: str = ""
    framesSoldTrend: str = "up"


class StaffWarehouseReportsResponse(BaseModel):
    kpis: list[DashboardKpi]
    accuracyTrend: list[WeekPoint]
    dispatchedTrend: list[WeekPoint]


class ThroughputPoint(BaseModel):
    d: str
    inb: float
    out: float


class ZoneUse(BaseModel):
    zone: str
    used: float


class WarehouseActivity(BaseModel):
    id: str
    type: str
    vendor: str
    qty: int
    status: str


class StaffWarehouseDashboardResponse(BaseModel):
    kpis: list[DashboardKpi]
    throughput: list[ThroughputPoint]
    zones: list[ZoneUse]
    recentActivity: list[WarehouseActivity]
