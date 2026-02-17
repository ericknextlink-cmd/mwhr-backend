from sqlmodel import Field, SQLModel


class UpgradeCriteriaBase(SQLModel):
    text: str = Field(min_length=1)
    sort_order: int = Field(default=0, description="Lower = higher in list")


class UpgradeCriteria(UpgradeCriteriaBase, table=True):
    __tablename__ = "upgrade_criteria"
    id: int | None = Field(default=None, primary_key=True)


class UpgradeCriteriaCreate(UpgradeCriteriaBase):
    pass


class UpgradeCriteriaRead(UpgradeCriteriaBase):
    id: int


class UpgradeCriteriaUpdate(SQLModel):
    text: str | None = None
    sort_order: int | None = None
