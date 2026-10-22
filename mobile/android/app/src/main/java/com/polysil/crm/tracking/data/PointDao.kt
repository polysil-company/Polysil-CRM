package com.polysil.crm.tracking.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query

@Dao
interface PointDao {
    @Insert
    fun insert(point: PointEntity)

    @Query("SELECT * FROM points ORDER BY seq ASC LIMIT :limit")
    fun oldest(limit: Int): List<PointEntity>

    @Query("DELETE FROM points WHERE id IN (:ids)")
    fun delete(ids: List<String>)

    @Query("SELECT COUNT(*) FROM points")
    fun count(): Int
}
