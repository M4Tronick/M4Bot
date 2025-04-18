import json
from datetime import datetime
from models.db import Database
from utils.logger import logger

class ChannelPointsActivity:
    @staticmethod
    def add_activity(activity_data):
        """
        Adds a new activity record to the database
        
        Parameters:
        - channel_id: The channel identifier
        - user_id: The user identifier
        - username: The username
        - action_type: Type of action (redeem, earning, manual_adjustment, etc.)
        - points: Points amount
        - reward_id: Optional reward ID (for redemptions)
        - reward_name: Optional reward name (for redemptions)
        - action: For manual adjustments (add, remove, set)
        """
        try:
            db = Database()
            timestamp = datetime.now().isoformat()
            
            query = """
            INSERT INTO channel_points_activity 
            (channel_id, user_id, username, action_type, points, reward_id, reward_name, action, timestamp) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            values = (
                activity_data.get('channel_id'),
                activity_data.get('user_id'),
                activity_data.get('username'),
                activity_data.get('action_type'),
                activity_data.get('points'),
                activity_data.get('reward_id'),
                activity_data.get('reward_name'),
                activity_data.get('action'),
                timestamp
            )
            
            db.execute(query, values)
            db.commit()
            
            logger.info(f"Added activity for user {activity_data.get('username')} in channel {activity_data.get('channel_id')}")
            return True
        except Exception as e:
            logger.error(f"Error adding activity: {str(e)}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def get_activity_by_channel(channel_id, page=1, per_page=10):
        """
        Retrieves activity records for a channel with pagination
        
        Parameters:
        - channel_id: The channel identifier
        - page: Page number
        - per_page: Items per page
        
        Returns:
        - List of activity records
        - Total count of records
        """
        try:
            db = Database()
            
            # Get total count
            count_query = "SELECT COUNT(*) FROM channel_points_activity WHERE channel_id = %s"
            db.execute(count_query, (channel_id,))
            total = db.fetchone()[0]
            
            # Get paginated data
            offset = (page - 1) * per_page
            
            query = """
            SELECT id, user_id, username, action_type, points, reward_id, reward_name, action, timestamp
            FROM channel_points_activity
            WHERE channel_id = %s
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
            """
            
            db.execute(query, (channel_id, per_page, offset))
            rows = db.fetchall()
            
            activity = []
            for row in rows:
                activity_item = {
                    'id': row[0],
                    'user_id': row[1],
                    'username': row[2],
                    'action_type': row[3],
                    'points': row[4],
                    'reward_id': row[5],
                    'reward_name': row[6],
                    'action': row[7],
                    'timestamp': row[8]
                }
                activity.append(activity_item)
            
            return activity, total
        except Exception as e:
            logger.error(f"Error fetching activity: {str(e)}")
            return [], 0
        finally:
            db.close()
    
    @staticmethod
    def get_recent_activity_by_user(channel_id, user_id, limit=5):
        """
        Retrieves recent activity for a specific user
        
        Parameters:
        - channel_id: The channel identifier
        - user_id: The user identifier
        - limit: Maximum number of records to return
        
        Returns:
        - List of activity records
        """
        try:
            db = Database()
            
            query = """
            SELECT id, action_type, points, reward_id, reward_name, action, timestamp
            FROM channel_points_activity
            WHERE channel_id = %s AND user_id = %s
            ORDER BY timestamp DESC
            LIMIT %s
            """
            
            db.execute(query, (channel_id, user_id, limit))
            rows = db.fetchall()
            
            activity = []
            for row in rows:
                activity_item = {
                    'id': row[0],
                    'action_type': row[1],
                    'points': row[2],
                    'reward_id': row[3],
                    'reward_name': row[4],
                    'action': row[5],
                    'timestamp': row[6]
                }
                activity.append(activity_item)
            
            return activity
        except Exception as e:
            logger.error(f"Error fetching user activity: {str(e)}")
            return []
        finally:
            db.close() 